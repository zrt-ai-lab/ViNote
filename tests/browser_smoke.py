"""Opt-in browser checks against `python -m tests.smoke_server` only.

Requires Playwright plus Chrome (or set VINOTE_BROWSER_CHANNEL to chromium).
The fixture uses an isolated database and a deterministic model stand-in.
"""
import os
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright


BASE = "http://127.0.0.1:18999"


def main():
    completed = []
    errors = []
    with sync_playwright() as playwright:
        channel = os.getenv("VINOTE_BROWSER_CHANNEL", "chrome")
        browser = playwright.chromium.launch(
            headless=True, **({"channel": channel} if channel != "chromium" else {}),
        )

        def page_with_storage(values=None):
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            if values:
                import json
                context.add_init_script(
                    "for (const [k,v] of Object.entries(" + json.dumps(values) + ")) localStorage.setItem(k,v);"
                )
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            return context, page

        context, page = page_with_storage({"vinote.note.task-id": "abc123"})
        page.goto(BASE + "/note")
        expect(page.get_by_text("冒烟演示笔记", exact=True)).to_be_visible()
        for index, filename in ((0, "transcript_demo_abc123.md"), (1, "summary_demo_abc123.md")):
            with page.expect_download() as download:
                page.get_by_title("下载", exact=True).nth(index).click()
            assert download.value.suggested_filename == filename
            assert download.value.failure() is None
        completed.append("completed-task restoration and real artifact downloads")
        page.reload()
        expect(page.get_by_text("冒烟演示笔记", exact=True)).to_be_visible()
        page.route("**/download/*", lambda route: route.fulfill(status=404, json={"detail": "冒烟下载不存在"}))
        page.get_by_title("下载", exact=True).first.click()
        expect(page.get_by_text("冒烟下载不存在", exact=True)).to_be_visible()
        expect(page.get_by_text("文件已下载", exact=True)).to_have_count(0)
        completed.append("download HTTP failure is not reported as success")
        context.close()

        context, page = page_with_storage({"vinote.note.task-id": "smoke-running"})
        submissions = []
        status_requests = []
        page.on("request", lambda request: submissions.append(request.url)
                if request.method == "POST" and "/process-video" in request.url else None)
        page.on("request", lambda request: status_requests.append(request.url)
                if "/task-status/smoke-running" in request.url else None)
        page.route("**/api/task-stream/*", lambda route: route.abort())
        page.goto(BASE + "/note")
        expect(page.get_by_text("冒烟任务正在处理", exact=True)).to_be_visible()
        expect(page.get_by_text("已恢复状态查询，正在同步任务进度。", exact=True)).to_be_visible(timeout=12000)
        assert len(status_requests) >= 2 and not submissions
        page.reload()
        expect(page.get_by_text("冒烟任务正在处理", exact=True)).to_be_visible()
        assert not submissions
        completed.append("running-task refresh and disconnected SSE polling without resubmission")
        context.close()

        context, page = page_with_storage({
            "vinote.note.batch-id": "smoke-batch", "vinote.note.focused-id": "smoke-batch",
        })
        page.goto(BASE + "/note")
        expect(page.get_by_text("恢复中的批量任务", exact=True)).to_be_visible()
        page.reload()
        expect(page.get_by_text("恢复中的批量任务", exact=True)).to_be_visible()
        completed.append("batch progress restoration after refresh")
        context.close()

        context, page = page_with_storage()
        page.goto(BASE + "/history")
        search = page.get_by_placeholder("搜索标题、摘要或正文...")
        search.fill("蓝色卫星")
        expect(page.get_by_text("冒烟演示笔记", exact=True)).to_be_visible()
        expect(page.get_by_text("第二份演示笔记", exact=True)).to_be_visible()
        search.fill("绝对不存在的词语")
        expect(page.get_by_text("冒烟演示笔记", exact=True)).to_have_count(0)
        search.fill("光学芯片")
        expect(page.get_by_text("冒烟演示笔记", exact=True)).to_be_visible()
        completed.append("history searches late body text and summary, including no-result state")

        page.goto(BASE + "/qa")
        page.get_by_role("button", name="继续会话：冒烟历史会话", exact=True).click()
        expect(page.get_by_text("这是保存在 SQLite 的历史回答。", exact=True)).to_be_visible()
        session_id = parse_qs(urlparse(page.url).query)["sessionId"][0]
        page.reload()
        expect(page.get_by_text("这是保存在 SQLite 的历史回答。", exact=True)).to_be_visible()
        page.get_by_placeholder("输入你的问题...").fill("尾部事实是什么？")
        page.get_by_placeholder("输入你的问题...").press("Enter")
        expect(page.get_by_text("尾部事实是蓝色卫星。", exact=False)).to_be_visible()
        expect(page.get_by_role("button", name="删除会话：冒烟历史会话", exact=True)).to_be_enabled()
        stored = context.request.get(BASE + f"/api/qa/sessions/{session_id}").json()
        assert len(stored["messages"]) == 4
        assert "蓝色卫星" in stored["messages"][-1]["content"]
        completed.append("persistent QA continuation, late-evidence retrieval, streaming and SQLite save (fake LLM)")

        page.on("dialog", lambda dialog: dialog.accept())
        def failed_delete(route):
            if route.request.method == "DELETE":
                route.fulfill(status=500, json={"detail": "冒烟删除失败"})
            else:
                route.continue_()
        route_pattern = "**/api/qa/sessions/" + session_id
        page.route(route_pattern, failed_delete)
        page.get_by_role("button", name="删除会话：冒烟历史会话", exact=True).click()
        expect(page.get_by_text("冒烟删除失败", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name="继续会话：冒烟历史会话", exact=True)).to_be_visible()
        assert context.request.get(BASE + f"/api/qa/sessions/{session_id}").status == 200
        page.unroute(route_pattern, failed_delete)
        page.get_by_role("button", name="删除会话：冒烟历史会话", exact=True).click()
        expect(page.get_by_role("button", name="继续会话：冒烟历史会话", exact=True)).to_have_count(0)
        assert context.request.get(BASE + f"/api/qa/sessions/{session_id}").status == 404
        completed.append("session deletion: failure preserves state, confirmed success removes database record")
        assert context.request.get(BASE + "/api/tasks/completed?page_size=-1").status == 422
        completed.append("HTTP pagination validation")
        page.screenshot(path="/tmp/vinote-improve-browser-smoke.png", full_page=True)
        context.close()
        browser.close()
    assert not errors, errors
    for case in completed:
        print("PASS:", case)
    print(f"Browser smoke: {len(completed)} scenarios passed; no uncaught browser errors.")


if __name__ == "__main__":
    main()
