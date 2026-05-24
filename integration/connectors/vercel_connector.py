"""
Vercel Deployment Connector for Asirive Copartner — Phase 3 Integration
=========================================================================
Deploys frontend projects (Next.js, React, static HTML) to Vercel
via the Vercel REST API. No CLI required — API calls only.

Setup:
    VERCEL_TOKEN=...  in .env  (get from vercel.com/account/tokens)
    VERCEL_TEAM_ID=... in .env (optional — for team accounts)

Workflow:
    1. scaffold_result = scaffolder.scaffold("Landing page for Beanery coffee shop")
    2. deploy_result   = vercel.deploy(scaffold_result["output_path"], project_name="beanery")
    3. print(deploy_result["url"])  # https://beanery.vercel.app
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Copartner.Vercel")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not installed. Run: pip install httpx")

VERCEL_API = "https://api.vercel.com"


class VercelConnector:
    """
    Deploys projects to Vercel via REST API.

    Usage:
        vercel = VercelConnector(token="...")
        result = vercel.deploy(
            project_dir="output/beanery",
            project_name="beanery-coffee",
        )
        print(result["url"])  # live URL
    """

    def __init__(self, token: Optional[str] = None, team_id: Optional[str] = None):
        self.token   = token or os.environ.get("VERCEL_TOKEN", "")
        self.team_id = team_id or os.environ.get("VERCEL_TEAM_ID", "")
        self._ready  = bool(self.token)
        if not self._ready:
            logger.warning("VERCEL_TOKEN not set. Vercel deployment in demo mode.")

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _team_params(self) -> dict:
        return {"teamId": self.team_id} if self.team_id else {}

    def deploy(
        self,
        project_dir: str | Path,
        project_name: str,
        framework: str = "nextjs",
    ) -> dict:
        """
        Deploy a local project directory to Vercel.

        Args:
            project_dir:  Local path to the project root.
            project_name: Vercel project name (slug, e.g. "beanery-coffee").
            framework:    Vercel framework preset ("nextjs", "create-react-app", "static").

        Returns:
            dict with: url, deployment_id, status
        """
        if not self._ready:
            return self._demo_deploy(project_name)

        if not HTTPX_AVAILABLE:
            return {"error": "httpx not installed"}

        project_dir = Path(project_dir)
        if not project_dir.exists():
            return {"error": f"Project directory not found: {project_dir}"}

        try:
            # Collect all files as base64 for the Vercel Files API
            files = self._collect_files(project_dir)
            if not files:
                return {"error": "No files found in project directory"}

            logger.info(f"Deploying {len(files)} files to Vercel project '{project_name}'")

            with httpx.Client(timeout=60.0) as client:
                # Create deployment
                payload = {
                    "name":         project_name,
                    "files":        files,
                    "projectSettings": {
                        "framework": framework,
                    },
                    "target": "production",
                }

                resp = client.post(
                    f"{VERCEL_API}/v13/deployments",
                    headers=self._headers,
                    params=self._team_params(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            url    = f"https://{data.get('url', project_name + '.vercel.app')}"
            dep_id = data.get("id", "")

            logger.info(f"Deployed to Vercel: {url}")
            return {
                "url":           url,
                "deployment_id": dep_id,
                "status":        data.get("readyState", "BUILDING"),
                "project":       project_name,
            }

        except Exception as e:
            logger.error(f"Vercel deployment failed: {e}")
            return {"error": str(e)}

    def _collect_files(self, project_dir: Path) -> list[dict]:
        """
        Walk project directory and collect files for Vercel's Files API.
        Returns list of {file: relative_path, data: base64_content, encoding: "base64"}
        """
        import base64

        IGNORE = {
            "node_modules", ".git", ".next", "dist", "build",
            "__pycache__", ".venv", "venv",
        }
        MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

        files = []
        for path in project_dir.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORE for part in path.parts):
                continue
            if path.stat().st_size > MAX_FILE_SIZE:
                logger.debug(f"Skipping large file: {path}")
                continue

            rel = path.relative_to(project_dir).as_posix()
            try:
                content = path.read_bytes()
                files.append({
                    "file":     rel,
                    "data":     base64.b64encode(content).decode(),
                    "encoding": "base64",
                })
            except Exception as e:
                logger.debug(f"Could not read {rel}: {e}")

        return files

    def get_deployment_status(self, deployment_id: str) -> dict:
        """Check the status of a deployment."""
        if not self._ready or not HTTPX_AVAILABLE:
            return {"status": "demo", "deployment_id": deployment_id}
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{VERCEL_API}/v13/deployments/{deployment_id}",
                    headers=self._headers,
                    params=self._team_params(),
                )
                resp.raise_for_status()
                data = resp.json()
            return {
                "deployment_id": deployment_id,
                "status":        data.get("readyState", "UNKNOWN"),
                "url":           f"https://{data.get('url', '')}",
            }
        except Exception as e:
            return {"error": str(e)}

    def _demo_deploy(self, project_name: str) -> dict:
        """Return a fake deployment result when VERCEL_TOKEN is not set."""
        return {
            "url":           f"https://{project_name}.vercel.app",
            "deployment_id": "demo_dep_" + str(int(time.time())),
            "status":        "DEMO",
            "project":       project_name,
            "note":          "Set VERCEL_TOKEN in .env to enable real deployments",
        }
