// ---------------------------------------------------------------------------
// Author  : Anil Kalisetti
// Purpose : Declarative Jenkins pipeline. Credentials are injected from the Jenkins store
//           (IDs below are placeholders: create them under Manage Jenkins > Credentials).
// ---------------------------------------------------------------------------
pipeline {
    agent { dockerfile true }            // uses the repo Dockerfile: same image as local runs

    parameters {
        string(name: 'TAGS', defaultValue: 'not slow', description: 'Tag expression: smoke, uat, regression and not slow ...')
        string(name: 'BROWSERS', defaultValue: 'chrome,firefox', description: 'chrome,firefox,edge or all')
        choice(name: 'EXECUTION_MODE', choices: ['local', 'remote', 'saucelabs', 'browserstack', 'lambdatest'])
        booleanParam(name: 'RAISE_JIRA_DEFECTS', defaultValue: false)
    }

    triggers { cron('H 6 * * 1-5') }     // nightly regression on weekdays

    options {
        timeout(time: 60, unit: 'MINUTES')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    environment {
        EXECUTION_MODE = "${params.EXECUTION_MODE}"
        // TODO(cloud): create these credentials, then uncomment the ones you use.
        // SAUCE_USERNAME   = credentials('sauce-username')
        // SAUCE_ACCESS_KEY = credentials('sauce-access-key')
        // JIRA_API_TOKEN   = credentials('jira-api-token')
    }

    stages {
        stage('Offline checks') {
            steps { sh 'pytest -m "(unit or data or db) and not slow" -n auto' }
        }
        stage('Regression') {
            steps {
                sh """pytest --tags "${params.TAGS}" --ui-browsers "${params.BROWSERS}" -n 4 --reruns 1 --only-rerun WebDriverException \
                      --build-name "jenkins-${env.BUILD_NUMBER}" \
                      ${params.RAISE_JIRA_DEFECTS ? '--raise-jira-defects' : ''}"""
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'reports/junit.xml'
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
            publishHTML(target: [reportDir: 'reports', reportFiles: 'executive_summary.html',
                                 reportName: 'Executive Summary', keepAll: true, allowMissing: true])
            // Optional: install the Allure Jenkins plugin, then enable the next line.
            // allure results: [[path: 'reports/allure-results']]
        }
    }
}
