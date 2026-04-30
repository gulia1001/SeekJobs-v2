"""Minimal GitHub REST/GraphQL client used by the profile analyzer."""
import base64
import os

import requests


DEFAULT_TIMEOUT = 20


class GitHubAPIError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token=None, timeout=DEFAULT_TIMEOUT):
        self.base_url = "https://api.github.com"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "github-profile-resume-builder",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

        token = token or os.getenv("GITHUB_TOKEN")
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.token = token

    def _request(self, method, path, **kwargs):
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        if response.status_code >= 400:
            raise GitHubAPIError(self._build_error_message(response))
        return response

    @staticmethod
    def _build_error_message(response):
        try:
            payload = response.json()
            message = payload.get("message", response.text)
        except ValueError:
            message = response.text
        return f"GitHub API error {response.status_code}: {message}"

    def get_json(self, path, **kwargs):
        return self._request("GET", path, **kwargs).json()

    def paginate(self, path, params=None):
        page = 1
        items = []
        while True:
            page_params = {"per_page": 100, "page": page}
            if params:
                page_params.update(params)
            batch = self.get_json(path, params=page_params)
            if not batch:
                break
            if not isinstance(batch, list):
                raise GitHubAPIError(f"Expected list response for {path}")
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return items

    def get_user(self, username):
        return self.get_json(f"/users/{username}")

    def list_public_repos(self, username, include_forks=False):
        repos = self.paginate(
            f"/users/{username}/repos",
            params={"type": "owner", "sort": "updated"},
        )
        if include_forks:
            return repos
        return [repo for repo in repos if not repo.get("fork")]

    def get_repo(self, owner, repo):
        return self.get_json(f"/repos/{owner}/{repo}")

    def get_repo_languages(self, owner, repo):
        return self.get_json(f"/repos/{owner}/{repo}/languages")

    def get_repo_readme(self, owner, repo):
        response = self._request(
            "GET",
            f"/repos/{owner}/{repo}/readme",
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        return response.text

    def get_repo_contents(self, owner, repo, path="", ref=None):
        params = {}
        if ref:
            params["ref"] = ref
        suffix = f"/{path}" if path else ""
        return self.get_json(f"/repos/{owner}/{repo}/contents{suffix}", params=params)

    def get_root_files(self, owner, repo, ref=None):
        payload = self.get_repo_contents(owner, repo, ref=ref)
        if not isinstance(payload, list):
            return []
        return payload

    def get_file_text(self, owner, repo, path, ref=None):
        params = {}
        if ref:
            params["ref"] = ref
        payload = self.get_json(f"/repos/{owner}/{repo}/contents/{path}", params=params)
        content = payload.get("content")
        if not content or payload.get("encoding") != "base64":
            return None
        return base64.b64decode(content).decode("utf-8", errors="replace")

    def list_commits(self, owner, repo, author=None, max_pages=2):
        commits = []
        for page in range(1, max_pages + 1):
            params = {"per_page": 100, "page": page}
            if author:
                params["author"] = author
            batch = self.get_json(f"/repos/{owner}/{repo}/commits", params=params)
            if not isinstance(batch, list) or not batch:
                break
            commits.extend(batch)
            if len(batch) < 100:
                break
        return commits

    def get_pinned_repos(self, username):
        if not self.token:
            return []

        query = """
        query($login: String!) {
          user(login: $login) {
            pinnedItems(first: 6, types: REPOSITORY) {
              nodes {
                ... on Repository {
                  name
                }
              }
            }
          }
        }
        """
        payload = {"query": query, "variables": {"login": username}}
        response = self._request("POST", "https://api.github.com/graphql", json=payload)
        data = response.json()
        nodes = (
            data.get("data", {})
            .get("user", {})
            .get("pinnedItems", {})
            .get("nodes", [])
        )
        return [node["name"] for node in nodes if node and node.get("name")]
