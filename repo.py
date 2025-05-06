# pip install gitpython
# pip install atlassian-python-api
# pip install jira
# get api token and email for jira
# get git user and app password

import os
import re
import argparse
import logging
import csv
import time
import shutil
import json
from jira import JIRA
from git import Repo
from datetime import datetime
logging.basicConfig(level=logging.INFO)
# argument definitions
# execute as -> python repo.py -GIT_USER 'gituser' -GIT_PASS 'gitpassword' -JIRA_USER 'jirauser' -JIRA_PASS 'jirapassword'
start = time.time()
logging.info('Starting program')
argParser = argparse.ArgumentParser()
argParser.add_argument("-GIT_USER", "--GIT_USER", help="Your git user name")
argParser.add_argument("-GIT_PASS", "--GIT_PASS", help="Your git app password or app key")
argParser.add_argument("-JIRA_USER", "--JIRA_USER", help="Your jira user name")
argParser.add_argument("-JIRA_PASS", "--JIRA_PASS", help="Your jira password or app key")
args = argParser.parse_args()
GIT_USER = args.GIT_USER or None
GIT_PASS = args.GIT_PASS or None
JIRA_USER = args.JIRA_USER or None
JIRA_PASS = args.JIRA_PASS or None
logging.debug('Params provided: %s' % args)
if args.GIT_USER == None or args.GIT_PASS == None or args.JIRA_USER == None or args.JIRA_PASS == None:
  logging.info('Required command arguements missing, Terminating program')
  logging.info('Please use -h command to understand usage')
  quit()

# contants - to be read from config.json file
logging.info('Reading config from config.json')
try:
  with open('./config.json', 'r') as f:
    config_data = json.load(f)
    FIX_VERSION = config_data['FIX_VERSION'] or ''
    FOLDER_LOCATION = config_data['FOLDER_LOC'] or ''
    JIRA_URL = config_data['JIRA_URL'] or ''
    JIRA_PREFIX = JIRA_URL+'/browse/'
    GIT_WORKSPACE = config_data['GIT_WORKSPACE_URL'] or ''
    JQL_QUERY = config_data['JQL_QUERY'] or ''
    if FIX_VERSION == '' or FOLDER_LOCATION == '' or JIRA_URL == '' or GIT_WORKSPACE == '' or JQL_QUERY == '':
      logging.info('Required fields missing from config file, Terminating program')
      quit()
except FileNotFoundError:
  logging.info('File not found, Terminating program')
  quit()

# jira connection
logging.info('Connecting to JIRA server')
jiraObj = JIRA(options={'server': JIRA_URL}, basic_auth=(JIRA_USER, JIRA_PASS))
# get all jira keys for provided fix version
logging.info('Getting all issues for given fix version %s', FIX_VERSION)
jql_request = f'{JQL_QUERY} {FIX_VERSION} ORDER BY issuekey'
logging.debug('Running JQL query: %s', jql_request)
issues = jiraObj.search_issues(jql_request, maxResults= 100000, fields=['key'])
releaseJiraIds = []
for item in list(issues):
  releaseJiraIds.append(item.key)
releaseJiraIds = list(set(releaseJiraIds))
logging.debug('Jira IDs retrieved from server: %s', releaseJiraIds)

# file to read data for all repository from csv - repo_data.csv
logging.info('Reading file repo_data.csv')
csvData = []
try:
  with open("./repo_data.csv", 'r') as readFile:
    csvreader = list(csv.reader(readFile))
    if(len(csvreader) == 0):
      readFile.close()
      logging.info('No data in csv file: repo_data.csv')
      quit()
    elif(len(csvreader) == 1):
      readFile.close()
      logging.info('Only header present in csv file: repo_data.csv')
      quit()
    else:
      for row in csvreader:
        csvData.append(row)
      readFile.close()
except FileNotFoundError:
  logging.info('File not found: repo_data.csv')
  quit()

# create file to write results
logging.debug('Creating file for output results')
filename = f'execution_results_{datetime.now()}.csv'
wfile = open(filename, "w", encoding='UTF8')
writeFile = csv.writer(wfile)
header = ['Project name', 'Invalid commits', 'Invalid Jira Ids']
writeFile.writerow(header)

# actual code to validate details
logging.info('Processing data got from CSV file')
csvData.pop(0)
for row in csvData:
  logging.debug('processing row: %s', row)
  PROJECT_NAME = row[0]
  BRANCH_NAME = row[1] or 'master'
  REPO_LOCATION = f'{FOLDER_LOCATION}{PROJECT_NAME}'
  prevSha = row[2]
  currSha = row[3]
  logging.debug('Values provided: %s %s %s %s',PROJECT_NAME, BRANCH_NAME, prevSha, currSha)
  logging.info('Processing for %s', PROJECT_NAME)
  Repo.clone_from(f'https://{GIT_USER}:{GIT_PASS}@{GIT_WORKSPACE}{PROJECT_NAME}.git', REPO_LOCATION)
  repo = Repo(REPO_LOCATION)
  repo.git.checkout(BRANCH_NAME)
  gitPointer = repo.git
  commitref = prevSha + '..' + currSha
  # code to get data entries
  p = re.compile('(ENLA-)\d{5}', re.IGNORECASE)
  commits = gitPointer.log(commitref,'--no-merges','--pretty=format: %h | %ad% | %an | %s ')
  commitList = commits.split('\n')
  # remove cloned folder
  shutil.rmtree(REPO_LOCATION)
  invalidCommitList = []
  foundJiraList = []
  invalidJiraList = []
  logging.debug('Processing commits for %s', PROJECT_NAME)
  for commit in commitList:
    if(not re.search(p, commit)):
      invalidCommitList.append(commit)
    else:
      jiraId = re.search(p, commit).group(0).upper()
      foundJiraList.append(jiraId)
      singleIssue = jiraObj.issue(jiraId)
      if jiraId in releaseJiraIds: releaseJiraIds.remove(jiraId)
      if(len(singleIssue.fields.fixVersions) == 0 or FIX_VERSION != singleIssue.fields.fixVersions[0].name):
        invalidJiraList.append(re.search(p, commit).group(0))
  invalidJiraList = list(set(invalidJiraList))
  logging.debug('Invalid commits found %s', invalidCommitList)
  logging.debug('JIRA IDs found in commits %s', foundJiraList)
  logging.debug('Invalid JIRA IDs found %s', invalidJiraList)
  # writing to a file the results
  logging.info('Writing results to file for %s', PROJECT_NAME)
  data = [PROJECT_NAME, ('\n').join(invalidCommitList), ('\n').join([JIRA_PREFIX + i for i in invalidJiraList])]
  writeFile.writerow(data)
 
logging.info('Processing csv data complete')
logging.info('Writing final result to csv')
writeFile.writerow(['', '', ''])
writeFile.writerow(['NO COMMITS FOUND FOR BELOW JIRA'])
writeFile.writerow([('\n').join([JIRA_PREFIX + i for i in releaseJiraIds])])
logging.info('done...!!!')
end = time.time()
logging.info('Execution time --- %s seconds.', (end - start))
