import pytest

from app.core import config
from tests.utils import make_init_data


@pytest.mark.asyncio
async def test_topic_permissions(client):
    config.settings.bot_token = "test-bot-token"

    init_data_user1 = make_init_data(config.settings.bot_token, user_id=1)
    init_data_user2 = make_init_data(config.settings.bot_token, user_id=2)

    resp1 = await client.post("/auth/telegram", json={"init_data": init_data_user1})
    token1 = resp1.json()["access_token"]
    resp2 = await client.post("/auth/telegram", json={"init_data": init_data_user2})
    token2 = resp2.json()["access_token"]

    create = await client.post("/topics/", json={"title": "Biology"}, headers={"Authorization": f"Bearer {token1}"})
    topic_id = create.json()["id"]

    delete = await client.delete(f"/topics/{topic_id}", headers={"Authorization": f"Bearer {token2}"})
    assert delete.status_code == 404


@pytest.mark.asyncio
async def test_topic_file_count_excludes_deleted_files(client, tmp_path):
    config.settings.bot_token = "test-bot-token"
    config.settings.storage_path = str(tmp_path)

    init_data = make_init_data(config.settings.bot_token, user_id=123)
    auth = await client.post("/auth/telegram", json={"init_data": init_data})
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post("/topics/", json={"title": "Metrics"}, headers=headers)
    assert create.status_code == 200
    topic_id = create.json()["id"]

    upload = await client.post(
        f"/topics/{topic_id}/files/",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200
    file_id = upload.json()["id"]

    topics_after_upload = await client.get("/topics/", headers=headers)
    assert topics_after_upload.status_code == 200
    assert topics_after_upload.json()[0]["file_count"] == 1

    remove = await client.delete(f"/topics/{topic_id}/files/{file_id}", headers=headers)
    assert remove.status_code == 200

    files_after_delete = await client.get(f"/topics/{topic_id}/files/", headers=headers)
    assert files_after_delete.status_code == 200
    assert files_after_delete.json() == []

    topics_after_delete = await client.get("/topics/", headers=headers)
    assert topics_after_delete.status_code == 200
    assert topics_after_delete.json()[0]["file_count"] == 0
