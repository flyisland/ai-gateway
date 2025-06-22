# Convert to GitLab CI Workflow

## What It Does

Automatically converts Jenkins pipelines (Jenkinsfile) to GitLab CI/CD configurations.

## When to Use

- Migrating from Jenkins to GitLab
- Modernizing CI/CD pipelines
- Standardizing pipeline configurations
- Consolidating DevOps tools

## Supported Features

### Converts

- Pipeline stages and steps
- Environment variables
- Build triggers and parameters
- Artifacts and dependencies
- Parallel execution
- Conditional logic
- Post-build actions

### Maps Common Plugins

- Git → GitLab native
- Docker → GitLab Docker executor
- JUnit → GitLab test reports
- Credentials → CI/CD variables

## Example Conversion

### Jenkins Input

```groovy
pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                sh 'npm install'
                sh 'npm build'
            }
        }
        stage('Test') {
            steps {
                sh 'npm test'
            }
        }
        stage('Deploy') {
            when { branch 'main' }
            steps {
                sh './deploy.sh'
            }
        }
    }
}
```

### GitLab Output

```YAML
stages:
  - build
  - test
  - deploy

build:
  stage: build
  script:
    - npm install
    - npm build
  artifacts:
    paths:
      - node_modules/
      - dist/

test:
  stage: test
  script:
    - npm test

deploy:
  stage: deploy
  script:
    - ./deploy.sh
  only:
    - main
```

## How to Use

1. **Ensure Jenkinsfile is current** and working
1. **Run the workflow** on your project
1. **Review generated**`.gitlab-ci.yml`
1. **Test in development** environment
1. **Adjust** environment-specific settings
1. **Deploy** to production

## Best Practices

1. **Document dependencies** before migration
1. **List all credentials** that need migration
1. **Run both systems** in parallel initially
1. **Compare outputs** to ensure accuracy
1. **Update documentation** and train team
