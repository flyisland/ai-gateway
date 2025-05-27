"""
Tests for the Intelligent Dependency Risk Assessment Tool

This test suite demonstrates the functionality of the DependencyRiskAnalyzer
and validates its risk assessment capabilities.
"""

import pytest
import asyncio
import json
import sys
import os
from unittest.mock import Mock, AsyncMock

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from duo_workflow_service.tools.dependency_risk_analyzer import (
    DependencyRiskAnalyzer,
    RiskLevel,
    RecommendationType
)


class TestDependencyRiskAnalyzer:
    """Test suite for DependencyRiskAnalyzer tool."""

    @pytest.fixture
    def analyzer(self):
        """Create a DependencyRiskAnalyzer instance."""
        analyzer = DependencyRiskAnalyzer()
        # Mock the gitlab_client property
        mock_client = Mock()
        mock_client.aget = AsyncMock()
        analyzer.metadata = {"gitlab_client": mock_client, "gitlab_host": "gitlab.com"}
        return analyzer

    @pytest.mark.asyncio
    async def test_analyze_single_vulnerable_dependency(self, analyzer):
        """Test analysis of a single vulnerable dependency."""
        result_json = await analyzer._arun(
            project_path="test/project",
            dependency_name="lodash"
        )

        result = json.loads(result_json)
        assert result["success"] is True
        assert result["analysis_type"] == "single_dependency"
        assert result["dependency"]["name"] == "lodash"
        assert result["dependency"]["version"] == "4.17.20"

        # Check risk assessment
        risk_assessment = result["risk_assessment"]
        assert risk_assessment["level"] in ["medium", "high", "critical"]
        assert risk_assessment["score"] > 0
        assert risk_assessment["confidence"] > 0

        # Check risk factors
        factors = risk_assessment["factors"]
        assert len(factors) == 6  # All risk factors should be present
        factor_names = [f["name"] for f in factors]
        expected_factors = [
            "vulnerability_severity",
            "maintenance_status",
            "usage_patterns",
            "ecosystem_health",
            "compliance_risk",
            "supply_chain_risk"
        ]
        assert all(factor in factor_names for factor in expected_factors)

        # Check recommendations
        recommendations = result["recommendations"]
        assert len(recommendations) > 0

        # Should have security patch recommendation due to vulnerability
        security_patches = [r for r in recommendations if r["type"] == "security_patch"]
        assert len(security_patches) > 0
        assert security_patches[0]["priority"] == "high"

        # Check action items
        action_items = result["action_items"]
        assert len(action_items) > 0

        # Check summary
        assert "summary" in result
        assert "Risk Score:" in result["summary"]

    @pytest.mark.asyncio
    async def test_analyze_deprecated_dependency(self, analyzer):
        """Test analysis of a deprecated dependency (moment.js)."""
        result_json = await analyzer._arun(
            project_path="test/project",
            dependency_name="moment"
        )

        result = json.loads(result_json)
        assert result["success"] is True

        # Check that maintenance risk is high for deprecated package
        risk_factors = result["risk_assessment"]["factors"]
        maintenance_factor = next(f for f in risk_factors if f["name"] == "maintenance_status")
        assert maintenance_factor["score"] >= 80  # Should be high risk

        # Check for deprecation migration recommendation
        recommendations = result["recommendations"]
        migration_recs = [r for r in recommendations if r["type"] == "deprecation_migration"]
        assert len(migration_recs) > 0
        assert "deprecated" in migration_recs[0]["description"].lower()

    @pytest.mark.asyncio
    async def test_analyze_all_dependencies_project_overview(self, analyzer):
        """Test project-wide dependency analysis."""
        result_json = await analyzer._arun(
            project_path="test/project",
            risk_threshold="medium"
        )

        result = json.loads(result_json)
        assert result["success"] is True
        assert result["analysis_type"] == "project_overview"

        # Check summary statistics
        summary = result["summary"]
        assert "total_dependencies" in summary
        assert "high_risk_count" in summary
        assert "vulnerable_count" in summary
        assert "outdated_count" in summary
        assert "overall_risk_score" in summary
        assert "risk_distribution" in summary

        # Validate risk distribution
        risk_dist = summary["risk_distribution"]
        expected_levels = ["low", "medium", "high", "critical"]
        assert all(level in risk_dist for level in expected_levels)
        assert sum(risk_dist.values()) == summary["total_dependencies"]

        # Check high-risk dependencies details
        high_risk_deps = result["high_risk_dependencies"]
        assert isinstance(high_risk_deps, list)

        for dep in high_risk_deps:
            assert "name" in dep
            assert "risk_score" in dep
            assert "risk_level" in dep
            assert "primary_concerns" in dep
            assert "urgent_actions" in dep

        # Check priority actions
        priority_actions = result["priority_actions"]
        assert isinstance(priority_actions, list)

        # Check project recommendations
        recommendations = result["recommendations"]
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

    @pytest.mark.asyncio
    async def test_vulnerability_risk_assessment(self, analyzer):
        """Test vulnerability risk factor assessment."""
        # Test dependency with high-severity vulnerability
        dependency = {
            "name": "test-package",
            "version": "1.0.0",
            "vulnerabilities": [
                {
                    "severity": "critical",
                    "title": "Remote Code Execution vulnerability",
                    "url": "/vulnerabilities/1"
                },
                {
                    "severity": "high",
                    "title": "SQL Injection vulnerability",
                    "url": "/vulnerabilities/2"
                }
            ]
        }

        risk_factor = await analyzer._assess_vulnerability_risk(dependency)

        assert risk_factor.name == "vulnerability_severity"
        assert risk_factor.score >= 80  # Should be high risk
        assert risk_factor.weight == analyzer.RISK_WEIGHTS["vulnerability_severity"]
        assert len(risk_factor.evidence) > 0
        assert "2 vulnerabilities found" in risk_factor.evidence[0]

    @pytest.mark.asyncio
    async def test_maintenance_risk_assessment(self, analyzer):
        """Test maintenance risk factor assessment."""
        # Test deprecated package
        deprecated_dependency = {
            "name": "moment",
            "version": "2.24.0"
        }

        risk_factor = await analyzer._assess_maintenance_risk(deprecated_dependency)

        assert risk_factor.name == "maintenance_status"
        assert risk_factor.score >= 80  # Should be high risk for deprecated
        assert "deprecated" in risk_factor.evidence[0].lower()

        # Test non-deprecated package
        normal_dependency = {
            "name": "some-package",
            "version": "1.0.0"
        }

        risk_factor = await analyzer._assess_maintenance_risk(normal_dependency)
        assert risk_factor.score < 80  # Should be lower risk

    def test_usage_risk_assessment(self, analyzer):
        """Test usage pattern risk factor assessment."""
        # Test direct dependency
        direct_dependency = {
            "name": "test-package",
            "location": {
                "top_level": True,
                "path": "package.json"
            }
        }

        risk_factor = analyzer._assess_usage_risk(direct_dependency)

        assert risk_factor.name == "usage_patterns"
        assert risk_factor.score >= 50  # Direct deps should have higher risk
        assert "Direct dependency" in risk_factor.evidence[0]

        # Test development dependency
        dev_dependency = {
            "name": "test-dev-package",
            "location": {
                "top_level": True,
                "path": "devDependencies"
            }
        }

        dev_risk_factor = analyzer._assess_usage_risk(dev_dependency)
        assert dev_risk_factor.score < risk_factor.score  # Dev deps should have lower risk

    def test_compliance_risk_assessment(self, analyzer):
        """Test compliance risk factor assessment."""
        # Test problematic license
        gpl_dependency = {
            "name": "gpl-package",
            "licenses": [{"name": "GPL-3.0"}]
        }

        risk_factor = analyzer._assess_compliance_risk(gpl_dependency)
        assert risk_factor.score >= 70  # GPL should be high risk

        # Test permissive license
        mit_dependency = {
            "name": "mit-package",
            "licenses": [{"name": "MIT"}]
        }

        mit_risk_factor = analyzer._assess_compliance_risk(mit_dependency)
        assert mit_risk_factor.score <= 20  # MIT should be low risk

    def test_supply_chain_risk_assessment(self, analyzer):
        """Test supply chain risk factor assessment."""
        # Test suspicious package name
        suspicious_dependency = {
            "name": "ab"  # Very short name
        }

        risk_factor = analyzer._assess_supply_chain_risk(suspicious_dependency)
        assert risk_factor.score >= 60  # Should be high risk

        # Test normal package name
        normal_dependency = {
            "name": "normal-package-name"
        }

        normal_risk_factor = analyzer._assess_supply_chain_risk(normal_dependency)
        assert normal_risk_factor.score < 50  # Should be lower risk

    @pytest.mark.asyncio
    async def test_upgrade_recommendations_generation(self, analyzer):
        """Test upgrade recommendation generation."""
        # Test vulnerable dependency
        vulnerable_dependency = {
            "name": "vulnerable-package",
            "version": "1.0.0",
            "vulnerabilities": [
                {"severity": "high", "title": "Security issue"}
            ]
        }

        recommendations = await analyzer._generate_upgrade_recommendations(
            vulnerable_dependency, []
        )

        # Should have security patch recommendation
        security_patches = [r for r in recommendations if r.type == RecommendationType.SECURITY_PATCH]
        assert len(security_patches) > 0
        assert security_patches[0].priority == "high"

        # Test deprecated dependency
        deprecated_dependency = {
            "name": "moment",
            "version": "2.24.0",
            "vulnerabilities": []
        }

        deprecated_recommendations = await analyzer._generate_upgrade_recommendations(
            deprecated_dependency, []
        )

        # Should have deprecation migration recommendation
        migration_recs = [r for r in deprecated_recommendations if r.type == RecommendationType.DEPRECATION_MIGRATION]
        assert len(migration_recs) > 0

    def test_risk_level_categorization(self, analyzer):
        """Test risk level categorization."""
        assert analyzer._categorize_risk_level(90) == RiskLevel.CRITICAL
        assert analyzer._categorize_risk_level(70) == RiskLevel.HIGH
        assert analyzer._categorize_risk_level(50) == RiskLevel.MEDIUM
        assert analyzer._categorize_risk_level(30) == RiskLevel.LOW

    def test_confidence_calculation(self, analyzer):
        """Test confidence level calculation."""
        from duo_workflow_service.tools.dependency_risk_analyzer import RiskFactor

        # High confidence factors (multiple evidence)
        high_conf_factors = [
            RiskFactor("test1", 50, 0.3, "desc", ["evidence1", "evidence2"]),
            RiskFactor("test2", 60, 0.3, "desc", ["evidence1", "evidence2", "evidence3"])
        ]

        confidence = analyzer._calculate_confidence_level(high_conf_factors)
        assert confidence >= 0.8

        # Low confidence factors (no evidence)
        low_conf_factors = [
            RiskFactor("test1", 50, 0.3, "desc", []),
            RiskFactor("test2", 60, 0.3, "desc", [])
        ]

        low_confidence = analyzer._calculate_confidence_level(low_conf_factors)
        assert low_confidence <= 0.5

    @pytest.mark.asyncio
    async def test_error_handling_missing_dependency(self, analyzer):
        """Test error handling for missing dependency."""
        result_json = await analyzer._arun(
            project_path="test/project",
            dependency_name="nonexistent-package"
        )

        result = json.loads(result_json)
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_filtering_by_risk_threshold(self, analyzer):
        """Test filtering dependencies by risk threshold."""
        # Test with high threshold
        high_threshold_json = await analyzer._arun(
            project_path="test/project",
            risk_threshold="high"
        )
        high_threshold_result = json.loads(high_threshold_json)

        # Test with low threshold
        low_threshold_json = await analyzer._arun(
            project_path="test/project",
            risk_threshold="low"
        )
        low_threshold_result = json.loads(low_threshold_json)

        # Low threshold should include more dependencies
        assert (low_threshold_result["summary"]["high_risk_count"] >=
                high_threshold_result["summary"]["high_risk_count"])

    @pytest.mark.asyncio
    async def test_analysis_scope_filtering(self, analyzer):
        """Test filtering by analysis scope."""
        # Test vulnerable scope
        vulnerable_json = await analyzer._arun(
            project_path="test/project",
            analysis_scope="vulnerable"
        )
        vulnerable_result = json.loads(vulnerable_json)

        # All dependencies in vulnerable scope should have vulnerabilities
        assert vulnerable_result["summary"]["vulnerable_count"] == vulnerable_result["summary"]["total_dependencies"]

        # Test all scope
        all_json = await analyzer._arun(
            project_path="test/project",
            analysis_scope="all"
        )
        all_result = json.loads(all_json)

        # All scope should include more dependencies
        assert all_result["summary"]["total_dependencies"] >= vulnerable_result["summary"]["total_dependencies"]

    def test_risk_distribution_calculation(self, analyzer):
        """Test risk distribution calculation."""
        from duo_workflow_service.tools.dependency_risk_analyzer import DependencyRiskAssessment

        assessments = [
            DependencyRiskAssessment("pkg1", "1.0", 90, RiskLevel.CRITICAL, [], [], [], 0.8),
            DependencyRiskAssessment("pkg2", "1.0", 70, RiskLevel.HIGH, [], [], [], 0.8),
            DependencyRiskAssessment("pkg3", "1.0", 50, RiskLevel.MEDIUM, [], [], [], 0.8),
            DependencyRiskAssessment("pkg4", "1.0", 30, RiskLevel.LOW, [], [], [], 0.8),
        ]

        distribution = analyzer._calculate_risk_distribution(assessments)

        assert distribution["critical"] == 1
        assert distribution["high"] == 1
        assert distribution["medium"] == 1
        assert distribution["low"] == 1

    def test_overall_risk_score_calculation(self, analyzer):
        """Test overall project risk score calculation."""
        from duo_workflow_service.tools.dependency_risk_analyzer import DependencyRiskAssessment

        assessments = [
            DependencyRiskAssessment("pkg1", "1.0", 80, RiskLevel.HIGH, [], [], [], 0.8),
            DependencyRiskAssessment("pkg2", "1.0", 60, RiskLevel.MEDIUM, [], [], [], 0.8),
            DependencyRiskAssessment("pkg3", "1.0", 40, RiskLevel.MEDIUM, [], [], [], 0.8),
        ]

        overall_score = analyzer._calculate_overall_risk_score(assessments)

        # Should be average of scores
        expected_score = (80 + 60 + 40) / 3
        assert abs(overall_score - expected_score) < 0.1

    def test_dependency_summary_generation(self, analyzer):
        """Test dependency summary generation."""
        from duo_workflow_service.tools.dependency_risk_analyzer import (
            DependencyRiskAssessment, RiskFactor, UpgradeRecommendation
        )

        risk_factors = [
            RiskFactor("vulnerability_severity", 80, 0.3, "High vulnerability risk", ["CVE found"]),
            RiskFactor("maintenance_status", 60, 0.2, "Moderate maintenance risk", ["Last update 6 months ago"])
        ]

        recommendations = [
            UpgradeRecommendation(
                RecommendationType.SECURITY_PATCH, "high", "1.0.1",
                "Apply security patch", [], "30 min", ["Fixes vulnerability"]
            )
        ]

        assessment = DependencyRiskAssessment(
            "test-package", "1.0.0", 75, RiskLevel.HIGH,
            risk_factors, recommendations, [], 0.8
        )

        summary = analyzer._generate_dependency_summary(assessment)

        assert "High Risk Score: 75/100" in summary
        assert "Key Risk Factors:" in summary
        assert "Immediate Recommendations:" in summary
        assert "🟠" in summary  # High risk emoji


if __name__ == "__main__":
    # Run a simple demonstration
    async def demo():
        """Demonstrate the DependencyRiskAnalyzer functionality."""
        print("🔍 GitLab Duo Intelligent Dependency Risk Assessment Demo")
        print("=" * 60)

        # Create analyzer instance
        analyzer = DependencyRiskAnalyzer()
        mock_client = Mock()
        mock_client.aget = AsyncMock()
        analyzer.metadata = {"gitlab_client": mock_client, "gitlab_host": "gitlab.com"}

        # Analyze a single vulnerable dependency
        print("\n📦 Analyzing lodash dependency...")
        result_json = await analyzer._arun(
            project_path="demo/project",
            dependency_name="lodash"
        )
        result = json.loads(result_json)

        if result["success"]:
            print(f"✅ Analysis completed successfully!")
            print(f"📊 Risk Score: {result['risk_assessment']['score']:.1f}/100")
            print(f"🎯 Risk Level: {result['risk_assessment']['level'].upper()}")
            print(f"🔬 Confidence: {result['risk_assessment']['confidence']:.1%}")

            print(f"\n📋 Recommendations ({len(result['recommendations'])} found):")
            for i, rec in enumerate(result['recommendations'][:3], 1):
                print(f"  {i}. [{rec['priority'].upper()}] {rec['description']}")

            print(f"\n⚡ Action Items ({len(result['action_items'])} found):")
            for action in result['action_items'][:2]:
                print(f"  • {action['description']} ({action['timeline']})")

        # Analyze all dependencies
        print(f"\n🏗️  Analyzing all project dependencies...")
        overview_json = await analyzer._arun(
            project_path="demo/project",
            risk_threshold="medium"
        )
        overview = json.loads(overview_json)

        if overview["success"]:
            summary = overview["summary"]
            print(f"✅ Project analysis completed!")
            print(f"📈 Total Dependencies: {summary['total_dependencies']}")
            print(f"🔴 High Risk: {summary['high_risk_count']}")
            print(f"⚠️  Vulnerable: {summary['vulnerable_count']}")
            print(f"📊 Overall Risk Score: {summary['overall_risk_score']:.1f}/100")

            print(f"\n🎯 Risk Distribution:")
            for level, count in summary['risk_distribution'].items():
                if count > 0:
                    print(f"  • {level.title()}: {count} dependencies")

        print(f"\n🎉 Demo completed! The tool provides comprehensive risk assessment")
        print(f"   and actionable recommendations for dependency management.")

    # Run the demo
    asyncio.run(demo())
