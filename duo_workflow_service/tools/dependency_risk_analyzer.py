"""
Intelligent Dependency Risk Assessment Tool for GitLab Duo

This tool analyzes project dependencies to provide AI-powered risk assessments,
upgrade recommendations, and security insights.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Type, ClassVar
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field
from duo_workflow_service.tools.duo_base_tool import DuoBaseTool

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecommendationType(Enum):
    SECURITY_PATCH = "security_patch"
    VERSION_UPGRADE = "version_upgrade"
    PACKAGE_REPLACEMENT = "package_replacement"
    DEPRECATION_MIGRATION = "deprecation_migration"


@dataclass
class RiskFactor:
    name: str
    score: float  # 0-100
    weight: float
    description: str
    evidence: List[str]


@dataclass
class UpgradeRecommendation:
    type: RecommendationType
    priority: str
    target_version: Optional[str]
    description: str
    breaking_changes: List[str]
    effort_estimate: str
    benefits: List[str]


@dataclass
class DependencyRiskAssessment:
    dependency_name: str
    current_version: str
    risk_score: float
    risk_level: RiskLevel
    risk_factors: List[RiskFactor]
    recommendations: List[UpgradeRecommendation]
    action_items: List[Dict[str, Any]]
    confidence: float


class DependencyRiskAnalyzerInput(BaseModel):
    project_path: str = Field(description="GitLab project path (e.g., 'group/project')")
    dependency_name: Optional[str] = Field(default=None, description="Specific dependency to analyze (optional)")
    analysis_scope: str = Field(default="all", description="Scope of analysis: 'all', 'vulnerable', or 'outdated'")
    risk_threshold: str = Field(default="medium", description="Risk threshold for filtering: 'low', 'medium', 'high', or 'critical'")


class DependencyRiskAnalyzer(DuoBaseTool):
    """
    AI-powered dependency risk assessment tool that analyzes project dependencies
    and provides intelligent recommendations for security improvements.
    """

    name: str = "dependency_risk_analyzer"
    description: str = "Analyze dependency risks and provide upgrade recommendations"
    args_schema: Type[BaseModel] = DependencyRiskAnalyzerInput  # type: ignore

    # Risk scoring weights
    RISK_WEIGHTS: ClassVar[Dict[str, float]] = {
        'vulnerability_severity': 0.30,
        'maintenance_status': 0.20,
        'usage_patterns': 0.15,
        'ecosystem_health': 0.15,
        'compliance_risk': 0.10,
        'supply_chain_risk': 0.10
    }

    # Known vulnerability patterns and risk indicators
    HIGH_RISK_PATTERNS: ClassVar[List[str]] = [
        'prototype pollution',
        'remote code execution',
        'sql injection',
        'cross-site scripting',
        'path traversal',
        'deserialization'
    ]

    DEPRECATED_PACKAGES: ClassVar[Dict[str, Dict[str, Any]]] = {
        'moment': {
            'alternatives': ['date-fns', 'dayjs', 'luxon'],
            'reason': 'Officially deprecated, maintenance mode only'
        },
        'request': {
            'alternatives': ['axios', 'node-fetch', 'got'],
            'reason': 'Deprecated, no longer maintained'
        },
        'bower': {
            'alternatives': ['npm', 'yarn'],
            'reason': 'Deprecated package manager'
        }
    }

    def __init__(self):
        super().__init__()
        # Use object.__setattr__ to bypass Pydantic's field validation
        object.__setattr__(self, 'vulnerability_db', self._load_vulnerability_database())

    async def _arun(
        self,
        project_path: str,
        dependency_name: Optional[str] = None,
        analysis_scope: str = "all",
        risk_threshold: str = "medium"
    ) -> str:
        """
        Execute dependency risk analysis.

        Args:
            project_path: GitLab project path
            dependency_name: Specific dependency to analyze (optional)
            analysis_scope: Scope of analysis ("all", "vulnerable", "outdated")
            risk_threshold: Risk threshold for filtering ("low", "medium", "high")

        Returns:
            Risk analysis results with recommendations
        """
        try:
            logger.info(f"Starting dependency risk analysis for project: {project_path}")

            # Fetch project and dependencies
            project = await self._fetch_project(project_path)
            dependencies = await self._fetch_dependencies(project, analysis_scope)

            if dependency_name:
                result = await self._analyze_single_dependency(dependencies, dependency_name)
            else:
                result = await self._analyze_all_dependencies(dependencies, risk_threshold)

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Error in dependency risk analysis: {str(e)}")
            error_result = {
                "error": f"Failed to analyze dependencies: {str(e)}",
                "success": False
            }
            return json.dumps(error_result, indent=2)

    def format_display_message(self, args: DependencyRiskAnalyzerInput) -> str:
        if args.dependency_name:
            return f"Analyzing dependency risk for '{args.dependency_name}' in project {args.project_path}"
        else:
            return f"Analyzing all dependencies in project {args.project_path} (scope: {args.analysis_scope}, threshold: {args.risk_threshold})"

    async def _analyze_single_dependency(
        self,
        dependencies: List[Dict],
        dependency_name: str
    ) -> Dict[str, Any]:
        """Analyze a single dependency in detail."""
        dependency = next((d for d in dependencies if d['name'] == dependency_name), None)

        if not dependency:
            return {
                "error": f"Dependency '{dependency_name}' not found in project",
                "success": False
            }

        risk_assessment = await self._calculate_risk_assessment(dependency)

        return {
            "success": True,
            "analysis_type": "single_dependency",
            "dependency": {
                "name": dependency['name'],
                "version": dependency['version'],
                "packager": dependency.get('packager', 'unknown')
            },
            "risk_assessment": {
                "score": risk_assessment.risk_score,
                "level": risk_assessment.risk_level.value,
                "confidence": risk_assessment.confidence,
                "factors": [
                    {
                        "name": factor.name,
                        "score": factor.score,
                        "weight": factor.weight,
                        "description": factor.description,
                        "evidence": factor.evidence
                    }
                    for factor in risk_assessment.risk_factors
                ]
            },
            "recommendations": [
                {
                    "type": rec.type.value,
                    "priority": rec.priority,
                    "target_version": rec.target_version,
                    "description": rec.description,
                    "breaking_changes": rec.breaking_changes,
                    "effort_estimate": rec.effort_estimate,
                    "benefits": rec.benefits
                }
                for rec in risk_assessment.recommendations
            ],
            "action_items": risk_assessment.action_items,
            "summary": self._generate_dependency_summary(risk_assessment)
        }

    async def _analyze_all_dependencies(
        self,
        dependencies: List[Dict],
        risk_threshold: str
    ) -> Dict[str, Any]:
        """Analyze all dependencies and provide project-level insights."""
        threshold_value = self._get_risk_threshold_value(risk_threshold)

        # Calculate risk scores for all dependencies
        risk_assessments = []
        for dep in dependencies:
            assessment = await self._calculate_risk_assessment(dep)
            risk_assessments.append(assessment)

        # Filter high-risk dependencies
        high_risk_deps = [
            assessment for assessment in risk_assessments
            if assessment.risk_score >= threshold_value
        ]

        # Generate project-level statistics
        vulnerable_deps = [dep for dep in dependencies if dep.get('vulnerability_count', 0) > 0]
        outdated_deps = await self._identify_outdated_dependencies(dependencies)

        return {
            "success": True,
            "analysis_type": "project_overview",
            "summary": {
                "total_dependencies": len(dependencies),
                "high_risk_count": len(high_risk_deps),
                "vulnerable_count": len(vulnerable_deps),
                "outdated_count": len(outdated_deps),
                "overall_risk_score": self._calculate_overall_risk_score(risk_assessments),
                "risk_distribution": self._calculate_risk_distribution(risk_assessments)
            },
            "high_risk_dependencies": [
                {
                    "name": assessment.dependency_name,
                    "risk_score": assessment.risk_score,
                    "risk_level": assessment.risk_level.value,
                    "primary_concerns": self._extract_primary_concerns(assessment),
                    "urgent_actions": [
                        action for action in assessment.action_items
                        if action.get('priority') in ['critical', 'high']
                    ]
                }
                for assessment in high_risk_deps[:10]  # Top 10 highest risk
            ],
            "priority_actions": self._generate_priority_actions(high_risk_deps),
            "recommendations": self._generate_project_recommendations(risk_assessments),
            "trends": await self._analyze_risk_trends(dependencies)
        }

    async def _calculate_risk_assessment(self, dependency: Dict) -> DependencyRiskAssessment:
        """Calculate comprehensive risk assessment for a dependency."""
        risk_factors = []

        # 1. Vulnerability Severity Assessment
        vuln_factor = await self._assess_vulnerability_risk(dependency)
        risk_factors.append(vuln_factor)

        # 2. Maintenance Status Assessment
        maintenance_factor = await self._assess_maintenance_risk(dependency)
        risk_factors.append(maintenance_factor)

        # 3. Usage Pattern Assessment
        usage_factor = self._assess_usage_risk(dependency)
        risk_factors.append(usage_factor)

        # 4. Ecosystem Health Assessment
        ecosystem_factor = await self._assess_ecosystem_risk(dependency)
        risk_factors.append(ecosystem_factor)

        # 5. Compliance Risk Assessment
        compliance_factor = self._assess_compliance_risk(dependency)
        risk_factors.append(compliance_factor)

        # 6. Supply Chain Risk Assessment
        supply_chain_factor = self._assess_supply_chain_risk(dependency)
        risk_factors.append(supply_chain_factor)

        # Calculate weighted risk score
        risk_score = sum(
            factor.score * factor.weight
            for factor in risk_factors
        )

        # Determine risk level
        risk_level = self._categorize_risk_level(risk_score)

        # Generate recommendations
        recommendations = await self._generate_upgrade_recommendations(dependency, risk_factors)

        # Generate action items
        action_items = self._generate_action_items(dependency, risk_score, risk_factors)

        # Calculate confidence level
        confidence = self._calculate_confidence_level(risk_factors)

        return DependencyRiskAssessment(
            dependency_name=dependency['name'],
            current_version=dependency['version'],
            risk_score=risk_score,
            risk_level=risk_level,
            risk_factors=risk_factors,
            recommendations=recommendations,
            action_items=action_items,
            confidence=confidence
        )

    async def _assess_vulnerability_risk(self, dependency: Dict) -> RiskFactor:
        """Assess vulnerability-related risks."""
        vulnerabilities = dependency.get('vulnerabilities', [])
        vuln_count = len(vulnerabilities)

        if vuln_count == 0:
            score = 10
            evidence = ["No known vulnerabilities"]
        else:
            # Calculate severity-weighted score
            severity_scores = {
                'critical': 100,
                'high': 80,
                'medium': 50,
                'low': 20,
                'info': 10
            }

            # Get the highest severity score
            max_severity = max(
                severity_scores.get(vuln.get('severity', 'medium').lower(), 50)
                for vuln in vulnerabilities
            )

            # Base score on highest severity, with multiplier for multiple vulnerabilities
            score = max_severity
            if vuln_count > 1:
                score = min(100, score * (1 + (vuln_count - 1) * 0.1))

            evidence = [
                f"{vuln_count} vulnerabilities found",
                f"Severities: {', '.join(v.get('severity', 'unknown') for v in vulnerabilities[:3])}"
            ]

            # Check for high-risk vulnerability patterns
            for vuln in vulnerabilities:
                title = vuln.get('title', '').lower()
                if any(pattern in title for pattern in self.HIGH_RISK_PATTERNS):
                    score = min(100, score * 1.2)
                    evidence.append(f"High-risk pattern detected: {vuln.get('title', 'Unknown')}")
                    break

        return RiskFactor(
            name="vulnerability_severity",
            score=score,
            weight=self.RISK_WEIGHTS['vulnerability_severity'],
            description="Assessment of known security vulnerabilities",
            evidence=evidence
        )

    async def _assess_maintenance_risk(self, dependency: Dict) -> RiskFactor:
        """Assess maintenance and support risks."""
        package_name = dependency['name']

        # Check if package is deprecated
        if package_name in self.DEPRECATED_PACKAGES:
            score = 90
            evidence = [
                f"Package is deprecated: {self.DEPRECATED_PACKAGES[package_name]['reason']}",
                f"Alternatives available: {', '.join(self.DEPRECATED_PACKAGES[package_name]['alternatives'])}"
            ]
        else:
            # Simulate maintenance assessment (in real implementation, would check package registries)
            score = 30  # Default moderate risk
            evidence = ["Maintenance status requires verification"]

        return RiskFactor(
            name="maintenance_status",
            score=score,
            weight=self.RISK_WEIGHTS['maintenance_status'],
            description="Assessment of package maintenance and support status",
            evidence=evidence
        )

    def _assess_usage_risk(self, dependency: Dict) -> RiskFactor:
        """Assess usage pattern risks."""
        location = dependency.get('location', {})
        is_top_level = location.get('top_level', False)

        if is_top_level:
            score = 60  # Direct dependencies have higher impact
            evidence = ["Direct dependency - high impact if compromised"]
        else:
            score = 30  # Transitive dependencies have lower direct impact
            evidence = ["Transitive dependency - moderate impact"]

        # Check for development vs production usage
        path = location.get('path', '')
        if 'devDependencies' in path or 'dev-dependencies' in path:
            score *= 0.7  # Reduce risk for dev-only dependencies
            evidence.append("Development-only dependency")
        else:
            evidence.append("Production dependency")

        return RiskFactor(
            name="usage_patterns",
            score=score,
            weight=self.RISK_WEIGHTS['usage_patterns'],
            description="Assessment of how the dependency is used in the project",
            evidence=evidence
        )

    async def _assess_ecosystem_risk(self, dependency: Dict) -> RiskFactor:
        """Assess ecosystem health risks."""
        # Simulate ecosystem health assessment
        # In real implementation, would check download stats, GitHub stars, etc.

        package_name = dependency['name']
        packager = dependency.get('packager', 'unknown')

        # Popular packages generally have lower ecosystem risk
        popular_packages = ['lodash', 'react', 'express', 'axios', 'moment']

        if package_name in popular_packages:
            score = 20
            evidence = ["Popular package with strong ecosystem support"]
        else:
            score = 40
            evidence = ["Ecosystem health requires verification"]

        return RiskFactor(
            name="ecosystem_health",
            score=score,
            weight=self.RISK_WEIGHTS['ecosystem_health'],
            description="Assessment of package ecosystem health and community support",
            evidence=evidence
        )

    def _assess_compliance_risk(self, dependency: Dict) -> RiskFactor:
        """Assess compliance and licensing risks."""
        licenses = dependency.get('licenses', [])

        if not licenses:
            score = 60
            evidence = ["No license information available"]
        else:
            # Check for problematic licenses
            problematic_licenses = ['GPL-3.0', 'AGPL-3.0', 'SSPL-1.0']
            permissive_licenses = ['MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause']

            license_names = [lic.get('name', '') for lic in licenses]

            if any(lic in problematic_licenses for lic in license_names):
                score = 80
                evidence = [f"Potentially problematic license: {', '.join(license_names)}"]
            elif any(lic in permissive_licenses for lic in license_names):
                score = 10
                evidence = [f"Permissive license: {', '.join(license_names)}"]
            else:
                score = 30
                evidence = [f"License requires review: {', '.join(license_names)}"]

        return RiskFactor(
            name="compliance_risk",
            score=score,
            weight=self.RISK_WEIGHTS['compliance_risk'],
            description="Assessment of licensing and compliance risks",
            evidence=evidence
        )

    def _assess_supply_chain_risk(self, dependency: Dict) -> RiskFactor:
        """Assess supply chain security risks."""
        package_name = dependency['name']

        # Check for typosquatting potential
        suspicious_patterns = [
            len(package_name) < 3,  # Very short names
            any(char.isdigit() for char in package_name[-2:]),  # Numbers at end
            package_name.count('-') > 3,  # Too many hyphens
        ]

        if any(suspicious_patterns):
            score = 70
            evidence = ["Package name has suspicious characteristics"]
        else:
            score = 25
            evidence = ["Package name appears legitimate"]

        return RiskFactor(
            name="supply_chain_risk",
            score=score,
            weight=self.RISK_WEIGHTS['supply_chain_risk'],
            description="Assessment of supply chain security risks",
            evidence=evidence
        )

    async def _generate_upgrade_recommendations(
        self,
        dependency: Dict,
        risk_factors: List[RiskFactor]
    ) -> List[UpgradeRecommendation]:
        """Generate upgrade recommendations based on risk assessment."""
        recommendations = []
        package_name = dependency['name']
        current_version = dependency['version']

        # Check for security patches
        vulnerabilities = dependency.get('vulnerabilities', [])
        if vulnerabilities:
            recommendations.append(UpgradeRecommendation(
                type=RecommendationType.SECURITY_PATCH,
                priority="high",
                target_version=f"{current_version}.1",  # Simulated patch version
                description=f"Upgrade to patch version to fix {len(vulnerabilities)} vulnerabilities",
                breaking_changes=[],
                effort_estimate="30 minutes",
                benefits=[
                    f"Fixes {len(vulnerabilities)} security vulnerabilities",
                    "Improves security posture",
                    "Minimal breaking changes expected"
                ]
            ))

        # Check for deprecated packages
        if package_name in self.DEPRECATED_PACKAGES:
            alternatives = self.DEPRECATED_PACKAGES[package_name]['alternatives']
            recommendations.append(UpgradeRecommendation(
                type=RecommendationType.DEPRECATION_MIGRATION,
                priority="medium",
                target_version=None,
                description=f"Migrate from deprecated {package_name} to modern alternative",
                breaking_changes=["API changes required", "Testing needed"],
                effort_estimate="2-4 hours",
                benefits=[
                    "Active maintenance and support",
                    "Better performance",
                    "Modern features and security"
                ]
            ))

        # General version upgrade recommendation
        if not vulnerabilities and package_name not in self.DEPRECATED_PACKAGES:
            recommendations.append(UpgradeRecommendation(
                type=RecommendationType.VERSION_UPGRADE,
                priority="low",
                target_version="latest",
                description="Consider upgrading to latest stable version",
                breaking_changes=["Review changelog for breaking changes"],
                effort_estimate="1-2 hours",
                benefits=[
                    "Latest features and improvements",
                    "Bug fixes",
                    "Performance optimizations"
                ]
            ))

        return recommendations

    def _generate_action_items(
        self,
        dependency: Dict,
        risk_score: float,
        risk_factors: List[RiskFactor]
    ) -> List[Dict[str, Any]]:
        """Generate prioritized action items."""
        actions = []

        if risk_score >= 80:
            actions.append({
                "priority": "critical",
                "action": "immediate_review",
                "description": f"Immediately review and address high-risk dependency {dependency['name']}",
                "timeline": "within 24 hours",
                "assignee": "security-team"
            })

        if risk_score >= 60:
            actions.append({
                "priority": "high",
                "action": "schedule_upgrade",
                "description": f"Schedule upgrade for {dependency['name']} in next sprint",
                "timeline": "within 1 week",
                "assignee": "development-team"
            })

        # Add specific actions based on risk factors
        for factor in risk_factors:
            if factor.score >= 70:
                if factor.name == "vulnerability_severity":
                    actions.append({
                        "priority": "high",
                        "action": "security_patch",
                        "description": f"Apply security patches for {dependency['name']}",
                        "timeline": "within 3 days",
                        "assignee": "security-team"
                    })
                elif factor.name == "maintenance_status":
                    actions.append({
                        "priority": "medium",
                        "action": "evaluate_alternatives",
                        "description": f"Evaluate alternatives to {dependency['name']}",
                        "timeline": "within 2 weeks",
                        "assignee": "architecture-team"
                    })

        return actions

    def _categorize_risk_level(self, risk_score: float) -> RiskLevel:
        """Categorize risk score into risk levels."""
        if risk_score >= 80:
            return RiskLevel.CRITICAL
        elif risk_score >= 60:
            return RiskLevel.HIGH
        elif risk_score >= 40:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _calculate_confidence_level(self, risk_factors: List[RiskFactor]) -> float:
        """Calculate confidence level of the risk assessment."""
        # Confidence based on availability of data for each factor
        confidence_scores = []

        for factor in risk_factors:
            if factor.evidence and len(factor.evidence) > 1:
                confidence_scores.append(0.9)
            elif factor.evidence:
                confidence_scores.append(0.7)
            else:
                confidence_scores.append(0.3)

        return sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5

    def _get_risk_threshold_value(self, threshold: str) -> float:
        """Convert risk threshold string to numeric value."""
        thresholds = {
            'low': 20,
            'medium': 40,
            'high': 60,
            'critical': 80
        }
        return thresholds.get(threshold, 40)

    def _calculate_overall_risk_score(self, assessments: List[DependencyRiskAssessment]) -> float:
        """Calculate project-level overall risk score."""
        if not assessments:
            return 0

        # Weight by dependency importance (direct vs transitive)
        weighted_scores = []
        for assessment in assessments:
            # Simplified weighting - in practice would consider usage patterns
            weight = 1.0
            weighted_scores.append(assessment.risk_score * weight)

        return sum(weighted_scores) / len(weighted_scores)

    def _calculate_risk_distribution(self, assessments: List[DependencyRiskAssessment]) -> Dict[str, int]:
        """Calculate distribution of dependencies by risk level."""
        distribution = {level.value: 0 for level in RiskLevel}

        for assessment in assessments:
            distribution[assessment.risk_level.value] += 1

        return distribution

    def _extract_primary_concerns(self, assessment: DependencyRiskAssessment) -> List[str]:
        """Extract primary concerns from risk assessment."""
        concerns = []

        for factor in assessment.risk_factors:
            if factor.score >= 70:
                concerns.append(f"{factor.name}: {factor.description}")

        return concerns[:3]  # Top 3 concerns

    def _generate_priority_actions(self, high_risk_deps: List[DependencyRiskAssessment]) -> List[Dict[str, Any]]:
        """Generate project-level priority actions."""
        actions = []

        if len(high_risk_deps) > 5:
            actions.append({
                "priority": "high",
                "action": "dependency_audit",
                "description": f"Conduct comprehensive audit of {len(high_risk_deps)} high-risk dependencies",
                "timeline": "this week"
            })

        vulnerable_deps = [
            dep for dep in high_risk_deps
            if any(factor.name == "vulnerability_severity" and factor.score >= 70 for factor in dep.risk_factors)
        ]

        if vulnerable_deps:
            actions.append({
                "priority": "critical",
                "action": "security_patches",
                "description": f"Apply security patches for {len(vulnerable_deps)} vulnerable dependencies",
                "timeline": "within 48 hours"
            })

        return actions

    def _generate_project_recommendations(self, assessments: List[DependencyRiskAssessment]) -> List[str]:
        """Generate project-level recommendations."""
        recommendations = []

        high_risk_count = len([a for a in assessments if a.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]])

        if high_risk_count > len(assessments) * 0.2:  # More than 20% high risk
            recommendations.append("Consider implementing stricter dependency approval policies")

        deprecated_count = len([
            a for a in assessments
            if any(factor.name == "maintenance_status" and factor.score >= 80 for factor in a.risk_factors)
        ])

        if deprecated_count > 0:
            recommendations.append(f"Plan migration for {deprecated_count} deprecated dependencies")

        recommendations.append("Implement automated dependency scanning in CI/CD pipeline")
        recommendations.append("Set up monitoring for new vulnerabilities in existing dependencies")

        return recommendations

    async def _analyze_risk_trends(self, dependencies: List[Dict]) -> Dict[str, Any]:
        """Analyze risk trends over time."""
        # Simplified trend analysis - in practice would use historical data
        return {
            "trend_direction": "stable",
            "risk_velocity": 0.0,
            "prediction": "Risk levels expected to remain stable with current practices"
        }

    def _generate_dependency_summary(self, assessment: DependencyRiskAssessment) -> str:
        """Generate human-readable summary of dependency risk assessment."""
        risk_emoji = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🟠",
            RiskLevel.CRITICAL: "🔴"
        }

        emoji = risk_emoji[assessment.risk_level]

        summary = f"{emoji} **{assessment.risk_level.value.title()} Risk Score: {assessment.risk_score:.0f}/100**\n\n"

        # Add top risk factors
        top_factors = sorted(assessment.risk_factors, key=lambda x: x.score, reverse=True)[:3]
        summary += "**Key Risk Factors:**\n"
        for factor in top_factors:
            if factor.score >= 50:
                summary += f"• **{factor.name.replace('_', ' ').title()}**: {factor.description}\n"

        # Add urgent recommendations
        urgent_recs = [r for r in assessment.recommendations if r.priority in ['high', 'critical']]
        if urgent_recs:
            summary += "\n**Immediate Recommendations:**\n"
            for i, rec in enumerate(urgent_recs[:2], 1):
                summary += f"{i}. {rec.description}\n"

        return summary

    async def _fetch_project(self, project_path: str) -> Dict:
        """Fetch project information from GitLab API."""
        # Simulate project fetch
        return {
            "id": 123,
            "path": project_path,
            "name": project_path.split('/')[-1]
        }

    async def _fetch_dependencies(self, project: Dict, scope: str) -> List[Dict]:
        """Fetch dependencies from GitLab API."""
        # Simulate dependency fetch with sample data
        sample_dependencies = [
            {
                "name": "lodash",
                "version": "4.17.20",
                "packager": "npm",
                "vulnerabilities": [
                    {
                        "id": 1,
                        "severity": "high",
                        "title": "Prototype Pollution in lodash",
                        "url": "/vulnerabilities/1"
                    }
                ],
                "licenses": [{"name": "MIT", "spdx_identifier": "MIT"}],
                "location": {"path": "package.json", "top_level": True},
                "vulnerability_count": 1
            },
            {
                "name": "moment",
                "version": "2.24.0",
                "packager": "npm",
                "vulnerabilities": [],
                "licenses": [{"name": "MIT", "spdx_identifier": "MIT"}],
                "location": {"path": "package.json", "top_level": True},
                "vulnerability_count": 0
            },
            {
                "name": "express",
                "version": "4.16.4",
                "packager": "npm",
                "vulnerabilities": [
                    {
                        "id": 2,
                        "severity": "medium",
                        "title": "Express.js vulnerability",
                        "url": "/vulnerabilities/2"
                    }
                ],
                "licenses": [{"name": "MIT", "spdx_identifier": "MIT"}],
                "location": {"path": "package.json", "top_level": True},
                "vulnerability_count": 1
            }
        ]

        if scope == "vulnerable":
            return [dep for dep in sample_dependencies if dep['vulnerability_count'] > 0]
        elif scope == "outdated":
            # Simulate outdated check
            return sample_dependencies
        else:
            return sample_dependencies

    async def _identify_outdated_dependencies(self, dependencies: List[Dict]) -> List[Dict]:
        """Identify outdated dependencies."""
        # Simulate outdated dependency identification
        return [dep for dep in dependencies if dep['name'] in ['moment', 'lodash']]

    def _load_vulnerability_database(self) -> Dict:
        """Load vulnerability database for analysis."""
        # Simplified vulnerability database
        return {
            "lodash": {
                "4.17.20": ["CVE-2021-23337"],
                "4.17.19": ["CVE-2020-8203", "CVE-2021-23337"]
            },
            "express": {
                "4.16.4": ["CVE-2022-24999"]
            }
        }
