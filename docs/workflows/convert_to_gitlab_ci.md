# Convert to GitLab CI Workflow

## What It Does

Automatically converts Jenkins pipelines (Jenkinsfile) to GitLab CI/CD configurations (.gitlab-ci.yml).

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

```yaml
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
2. **Run the workflow** on your project
3. **Review generated** `.gitlab-ci.yml`
4. **Test in development** environment
5. **Adjust** environment-specific settings
6. **Deploy** to production

## Key Mappings

| Jenkins      | GitLab CI                 |
|--------------|---------------------------|
| `agent`      | `image` or `tags`         |
| `when`       | `rules` or `only/except`  |
| `parallel`   | Multiple jobs, same stage |
| `parameters` | CI/CD variables           |
| `post`       | `after_script`            |

## Best Practices

1. **Document dependencies** before migration
2. **List all credentials** that need migration
3. **Run both systems** in parallel initially
4. **Compare outputs** to ensure accuracy
5. **Update documentation** and train team

## Common Issues

**Credentials not working?**

- Migrate to GitLab CI/CD variables
- Update references in scripts

**Complex Groovy scripts?**

- May need manual translation
- Consider simplifying logic

**Missing plugin equivalent?**

- Find GitLab-native alternatives
- Check GitLab marketplace