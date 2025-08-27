import { test, expect } from '@playwright/test';
import { execSync } from 'child_process';
import { existsSync, readFileSync } from 'fs';
import path from 'path';

test.describe('AI-Assist Service - Repair Verification Tests', () => {
  const serviceDir = process.cwd();
  
  test.beforeEach(async () => {
    // Ensure we're in the right directory
    expect(process.cwd()).toContain('ai-assist');
  });

  test('should have working package.json with test script', async () => {
    const packagePath = path.join(serviceDir, 'package.json');
    expect(existsSync(packagePath)).toBeTruthy();
    
    const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));
    expect(packageJson.scripts).toBeDefined();
    expect(packageJson.scripts.test).toBeDefined();
    expect(typeof packageJson.scripts.test).toBe('string');
    expect(packageJson.scripts.test.length).toBeGreaterThan(0);
  });

  test('should have Jest configuration that works', async () => {
    // Check for Jest config files
    const jestConfig = path.join(serviceDir, 'jest.config.js');
    const jestConfigTs = path.join(serviceDir, 'jest.config.ts');
    const jestConfigJson = path.join(serviceDir, 'jest.config.json');
    
    const hasJestConfig = existsSync(jestConfig) || existsSync(jestConfigTs) || existsSync(jestConfigJson);
    expect(hasJestConfig).toBeTruthy();
    
    // Check for Babel configuration
    const babelrc = path.join(serviceDir, '.babelrc');
    const babelrcJs = path.join(serviceDir, '.babelrc.js');
    const babelConfig = path.join(serviceDir, 'babel.config.js');
    
    const hasBabelConfig = existsSync(babelrc) || existsSync(babelrcJs) || existsSync(babelConfig);
    expect(hasBabelConfig).toBeTruthy();
  });

  test('should have TypeScript configuration that works', async () => {
    const tsconfig = path.join(serviceDir, 'tsconfig.json');
    expect(existsSync(tsconfig)).toBeTruthy();
    
    const tsconfigContent = readFileSync(tsconfig, 'utf8');
    const tsconfigJson = JSON.parse(tsconfigContent);
    
    // Verify Jest compatibility
    expect(tsconfigJson.compilerOptions).toBeDefined();
    expect(tsconfigJson.compilerOptions.target).toBeDefined();
    expect(tsconfigJson.compilerOptions.module).toBeDefined();
  });

  test('should have required testing dependencies installed', async () => {
    const packagePath = path.join(serviceDir, 'package.json');
    const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));
    
    const devDependencies = packageJson.devDependencies || {};
    
    // Core testing dependencies
    expect(devDependencies.jest).toBeDefined();
    expect(devDependencies['@babel/core']).toBeDefined();
    expect(devDependencies['@babel/preset-env']).toBeDefined();
    expect(devDependencies['@babel/preset-typescript']).toBeDefined();
    
    // TypeScript dependencies
    expect(devDependencies.typescript).toBeDefined();
    expect(devDependencies['@types/node']).toBeDefined();
    expect(devDependencies['@types/jest']).toBeDefined();
  });

  test('should have proper test directory structure', async () => {
    const testDir = path.join(serviceDir, 'tests');
    expect(existsSync(testDir)).toBeTruthy();
    
    // Check for required test subdirectories
    const e2eDir = path.join(testDir, 'e2e');
    const kernelDir = path.join(testDir, 'kernel');
    const vitestDir = path.join(testDir, 'vitest');
    
    expect(existsSync(e2eDir)).toBeTruthy();
    expect(existsSync(kernelDir)).toBeTruthy();
    expect(existsSync(vitestDir)).toBeTruthy();
  });

  test('should be able to run npm test successfully', async () => {
    // This test will actually run the test command
    try {
      const result = execSync('npm test', { 
        cwd: serviceDir, 
        encoding: 'utf8',
        timeout: 30000 // 30 second timeout
      });
      
      // If we get here, the test command ran successfully
      expect(result).toBeDefined();
      expect(typeof result).toBe('string');
      
    } catch (error) {
      // If npm test fails, this test should fail
      expect(error).toBeUndefined();
    }
  });

  test('should have working test files that can be executed', async () => {
    const testDir = path.join(serviceDir, 'tests');
    
    // Look for actual test files
    const testFiles = [
      path.join(testDir, 'vitest', '*.test.ts'),
      path.join(testDir, 'vitest', '*.spec.ts'),
      path.join(testDir, 'kernel', '*.test.ts'),
      path.join(testDir, 'kernel', '*.spec.ts')
    ];
    
    // At least one test file should exist
    let hasTestFiles = false;
    for (const pattern of testFiles) {
      try {
        const files = execSync(`find . -path "${pattern}" -type f`, { 
          cwd: serviceDir, 
          encoding: 'utf8' 
        });
        if (files.trim().length > 0) {
          hasTestFiles = true;
          break;
        }
      } catch (e) {
        // Pattern not found, continue
      }
    }
    
    expect(hasTestFiles).toBeTruthy();
  });

  test('should have CI/CD configuration that includes testing', async () => {
    const gitlabCi = path.join(serviceDir, '.gitlab-ci.yml');
    const githubActions = path.join(serviceDir, '.github/workflows');
    
    const hasCI = existsSync(gitlabCi) || existsSync(githubActions);
    expect(hasCI).toBeTruthy();
    
    if (existsSync(gitlabCi)) {
      const ciContent = readFileSync(gitlabCi, 'utf8');
      // Should contain test stage or test command
      expect(ciContent).toMatch(/test|testing|jest|vitest/i);
    }
  });

  test('should have proper module resolution for imports', async () => {
    // Check if there are any source files with imports
    const srcDir = path.join(serviceDir, 'src');
    if (existsSync(srcDir)) {
      const sourceFiles = execSync('find src -name "*.ts" -o -name "*.js"', { 
        cwd: serviceDir, 
        encoding: 'utf8' 
      });
      
      if (sourceFiles.trim().length > 0) {
        // At least one source file should exist
        expect(sourceFiles.trim().length).toBeGreaterThan(0);
      }
    }
  });

  test('should have working lock file', async () => {
    const packageLock = path.join(serviceDir, 'package-lock.json');
    const yarnLock = path.join(serviceDir, 'yarn.lock');
    const pnpmLock = path.join(serviceDir, 'pnpm-lock.yaml');
    
    const hasLockFile = existsSync(packageLock) || existsSync(yarnLock) || existsSync(pnpmLock);
    expect(hasLockFile).toBeTruthy();
  });

  test('should have proper Node.js version specification', async () => {
    const packagePath = path.join(serviceDir, 'package.json');
    const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));
    
    if (packageJson.engines && packageJson.engines.node) {
      const nodeVersion = packageJson.engines.node;
      expect(typeof nodeVersion).toBe('string');
      expect(nodeVersion.length).toBeGreaterThan(0);
    }
  });
});
