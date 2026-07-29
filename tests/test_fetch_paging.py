from copy import deepcopy

import httpx

from app.clients.freelancer import FreelancerClient, mock_projects
from app.core.config import Settings
from app.models import Project
from app.services.project_service import ProjectService


def test_live_client_paginates_a_large_fetch(settings) -> None:
    source = [{"id": item_id, "title": f"Project {item_id}"} for item_id in range(250)]
    offsets: list[int] = []
    live_settings = settings.model_copy(
        update={"freelancer_mock_mode": False, "freelancer_access_token": "test-token", "freelancer_fetch_limit": 300}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params.get("limit", "100"))
        offsets.append(offset)
        return httpx.Response(200, json={"result": {"projects": source[offset:offset + limit], "users": {}}})

    client = FreelancerClient(live_settings, httpx.Client(transport=httpx.MockTransport(handler)))
    projects = client.search_active_projects(limit=250)

    assert [project["id"] for project in projects] == list(range(250))
    assert offsets == [0, 100, 200]


def test_fetch_cursor_moves_to_unseen_pages_and_skips_known_projects(db, settings) -> None:
    class PagedFreelancer:
        def __init__(self) -> None:
            self.offsets: list[int] = []

        def search_active_projects(self, *, offset: int, **_kwargs):
            self.offsets.append(offset)
            page = deepcopy(mock_projects())
            for index, project in enumerate(page):
                project_id = 2000000 + offset + index
                project["id"] = project_id
                project["seo_url"] = f"page-{offset}-project-{index}"
            return page

    paged = PagedFreelancer()
    small_batch_settings = settings.model_copy(update={"freelancer_fetch_limit": 3})
    service = ProjectService(db, small_batch_settings, freelancer=paged)

    first = service.fetch_projects()
    second = service.fetch_projects()

    assert paged.offsets == [0, 3]
    assert first["new"] == 3
    assert second["new"] == 3
    assert second["known_skipped"] == 0
    assert db.query(Project).count() == 6
