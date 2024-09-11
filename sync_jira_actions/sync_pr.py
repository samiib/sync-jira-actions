#!/usr/bin/env python3
#
# Copyright 2019-2024 Espressif Systems (Shanghai) CO LTD
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import os
import re
import requests

from github import Github
from sync_issue import _create_jira_issue
from sync_issue import _find_jira_issue


def sync_remain_prs(jira):
    """
    Sync remain PRs (i.e. PRs without any comments) to Jira
    """
    github = Github(os.environ['GITHUB_TOKEN'])
    repo = github.get_repo(os.environ['GITHUB_REPOSITORY'])
    prs = repo.get_pulls(state='open', sort='created', direction='desc')
    for pr in prs:
        if not repo.has_in_collaborators(pr.user.login):
            # mock a github issue using current PR
            gh_issue = {
                'pull_request': True,
                'labels': [{'name': lbl.name} for lbl in pr.labels],
                'number': pr.number,
                'title': pr.title,
                'html_url': pr.html_url,
                'user': {'login': pr.user.login},
                'state': pr.state,
                'body': pr.body,
            }
            issue = _find_jira_issue(jira, gh_issue)
            if issue is None:
                _create_jira_issue(jira, gh_issue)


def find_and_link_pr_issues(gh_issue):
    """
    Finds any linked issues that will be closed by a PR then adds the Jira issues to the title
    This allows auto linking of PR's to related Jira issues.
    """
    token = os.environ['GITHUB_TOKEN']
    project = os.environ['JIRA_PROJECT']
    github = Github(os.environ['GITHUB_TOKEN'])
    repo = github.get_repo(os.environ['GITHUB_REPOSITORY'])
    pr_number = int(gh_issue['number'])
    pr_title = gh_issue['title']
    closing_issues = __find_closing_issues(token, repo.owner.login, repo.name, pr_number)
    jira_keys = []
    for issue in closing_issues:
        title = issue.get('title')
        match = re.search(f'.*({project}-\d*).*', title)
        if match:
            jira_key = match.group(1)
            print(f"Found linked issue: {jira_key}")
            jira_keys.append(jira_key)
    if len(jira_keys) > 0:
        new_pr_title = re.sub(f'{project}-\d*', '', pr_title)
        new_pr_title = re.sub('\(\s*\)', '', new_pr_title).strip()
        new_pr_title = f'{new_pr_title} ({" ".join(jira_keys)})'
        print(f'New PR title: {new_pr_title}')
        repo.get_issue(pr_number).edit(title=new_pr_title)
        return True
    return False


def __find_closing_issues(token, owner, repo, pr):
    headers = {"Authorization": f"Bearer {token}"}
    vars = {"owner": owner, "repo": repo, "pr": pr}
    query = """
        query($owner:String!, $repo:String!, $pr:Int!) {
            repository (owner: $owner, name: $repo) {
                pullRequest (number: $pr) {
                    closingIssuesReferences (first: 10) {
                        nodes {
                            number
                            title
                        }
                    }
                }
            }
        }
        """
    request = requests.post('https://api.github.com/graphql', json={'query': query, 'variables': vars}, headers=headers)
    if request.status_code == 200:
        closing_issues = request.json().get('data').get('repository').get('pullRequest').get('closingIssuesReferences').get('nodes')
        return closing_issues
    else:
        raise Exception("Query failed to run by returning code of {}. {}".format(request.status_code, query))