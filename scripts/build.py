#!/usr/bin/env python3
"""把文章和站点配置生成静态页面，并复制 projects/ 下的子项目。"""

import html
import json
import re
import shutil
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
POSTS_DIR = ROOT / "content" / "posts"
PROJECTS_DIR = ROOT / "projects"
SRC = ROOT / "src"

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")
PROJECT_HREF = re.compile(r"^/projects/([A-Za-z0-9][A-Za-z0-9_-]*)/$")


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def fill(template, values):
    def replace(match):
        key = match.group(1)
        if key not in values:
            fail(f"模板缺少占位符 {key}")
        return values[key]

    return PLACEHOLDER.sub(replace, template)


def parse_post(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    matched = FRONTMATTER.match(text)
    if not matched:
        fail(f"{path.name} 缺少 frontmatter")

    meta = {}
    for line in matched.group(1).splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            fail(f"{path.name} 的 frontmatter 无法解析：{line}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip("\"'")

    for key in ("title", "date", "summary"):
        if not meta.get(key):
            fail(f"{path.name} 缺少 {key}")
    if not DATE.match(meta["date"]):
        fail(f"{path.name} 的 date 需要是 YYYY-MM-DD")

    name_match = DATE_PREFIX.match(path.stem)
    slug = name_match.group(2) if name_match else path.stem
    if not SLUG.match(slug):
        fail(f"{path.name} 的文件名不能作为 URL")

    body = markdown.markdown(matched.group(2), extensions=["extra"])
    return {
        "title": meta["title"],
        "date": meta["date"],
        "summary": meta["summary"],
        "slug": slug,
        "html": body,
        "href": f"/blog/{slug}/",
    }


def load_posts():
    posts = []
    seen = set()
    for path in sorted(POSTS_DIR.glob("*.md")):
        post = parse_post(path)
        if post["slug"] in seen:
            fail(f"文章路径重复：/blog/{post['slug']}/")
        seen.add(post["slug"])
        posts.append(post)
    posts.sort(key=lambda item: item["date"], reverse=True)
    return posts


def load_site():
    try:
        site = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        fail(f"site.json 无法解析：{error}")
    for key in ("title", "description", "projects"):
        if key not in site:
            fail(f"site.json 缺少 {key}")
    if not isinstance(site["projects"], list):
        fail("site.json 的 projects 需要是数组")
    for project in site["projects"]:
        for key in ("name", "description", "href"):
            if not project.get(key):
                fail(f"项目条目缺少 {key}")
        if not PROJECT_HREF.match(project["href"]):
            fail(f"项目链接需要是 /projects/<name>/ ：{project['href']}")
    return site


def post_list(posts):
    if not posts:
        return '<p class="empty">还没有文章。</p>'
    items = []
    for post in posts:
        items.append(
            "<li>"
            f'<time datetime="{html.escape(post["date"])}">{html.escape(post["date"])}</time>'
            f'<a href="{html.escape(post["href"])}">{html.escape(post["title"])}</a>'
            f'<p class="summary">{html.escape(post["summary"])}</p>'
            "</li>"
        )
    return '<ul class="list">\n' + "\n".join(items) + "\n</ul>"


def projects_section(site):
    projects = site["projects"]
    if not projects:
        return ""
    items = []
    for project in projects:
        items.append(
            "<li>"
            f'<a href="{html.escape(project["href"])}">{html.escape(project["name"])}</a>'
            f'<p class="summary">{html.escape(project["description"])}</p>'
            "</li>"
        )
    return (
        '<section class="projects">\n<h2>项目</h2>\n<ul class="list">\n'
        + "\n".join(items)
        + "\n</ul>\n</section>"
    )


def render_page(site, page_title, content, current):
    layout = (SRC / "templates" / "layout.html").read_text(encoding="utf-8")
    document_title = site["title"] if page_title == site["title"] else f"{page_title} · {site['title']}"
    return fill(
        layout,
        {
            "title": html.escape(document_title),
            "description": html.escape(site["description"]),
            "site_title": html.escape(site["title"]),
            "home_current": ' aria-current="page"' if current == "home" else "",
            "blog_current": ' aria-current="page"' if current == "blog" else "",
            "content": content,
        },
    )


def write_page(relative_path, text):
    destination = DIST / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def has_site_files(directory):
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(directory)
        if any(part.startswith(".") for part in relative.parts):
            continue
        return True
    return False


def copy_projects(site):
    ignore = shutil.ignore_patterns(".*")
    copied = set()
    if PROJECTS_DIR.exists():
        for child in PROJECTS_DIR.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            if not has_site_files(child):
                continue
            shutil.copytree(child, DIST / "projects" / child.name, ignore=ignore)
            copied.add(child.name)

    for project in site["projects"]:
        name = PROJECT_HREF.match(project["href"]).group(1)
        index = PROJECTS_DIR / name / "index.html"
        if name not in copied or not index.is_file():
            fail(f"项目 {name} 需要放在 projects/{name}/，并且包含 index.html")


def build():
    site = load_site()
    posts = load_posts()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    articles = post_list(posts)
    home = (
        f"<h1>{html.escape(site['title'])}</h1>\n"
        f"<p class=\"lede\">{html.escape(site['description'])}</p>\n"
        "<section>\n<h2>文章</h2>\n"
        f"{articles}\n</section>\n"
        f"{projects_section(site)}"
    )
    write_page("index.html", render_page(site, site["title"], home, "home"))
    write_page("blog/index.html", render_page(site, "文章", f"<h1>文章</h1>\n{articles}", "blog"))

    for post in posts:
        article = (
            "<article>\n"
            f"<h1>{html.escape(post['title'])}</h1>\n"
            f"<time datetime=\"{html.escape(post['date'])}\">{html.escape(post['date'])}</time>\n"
            f"<div class=\"content\">\n{post['html']}\n</div>\n"
            "</article>"
        )
        write_page(
            f"blog/{post['slug']}/index.html",
            render_page(site, post["title"], article, "blog"),
        )

    missing = (
        "<h1>页面不存在</h1>\n"
        "<p>这个地址没有对应的页面。</p>\n"
        '<p><a href="/">返回首页</a></p>'
    )
    write_page("404.html", render_page(site, "页面不存在", missing, ""))
    shutil.copyfile(SRC / "style.css", DIST / "style.css")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    copy_projects(site)


if __name__ == "__main__":
    build()
