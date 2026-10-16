#!/usr/bin/env python3
"""把文章和站点配置生成静态页面，并复制 projects/ 下的子项目。"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
BVID = re.compile(r"BV[0-9A-Za-z]+")
APPLE_MUSIC = re.compile(r"^https://music\.apple\.com(/[a-z]{2}/[A-Za-z0-9%._~:/?#\[\]@!$&'()*+,;=-]+)$")
PHOTO_SRC = re.compile(r"^/images/[A-Za-z0-9][A-Za-z0-9._-]*$")
PHOTO_DATE = re.compile(r"^\d{4}(-\d{2}-\d{2})?$")
PHOTO_PAGE_SIZE = 6
HOME_LIMIT = 3


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

    tags = []
    if meta.get("tags"):
        tags = [part.strip() for part in meta["tags"].split(",") if part.strip()]

    body = markdown.markdown(matched.group(2), extensions=["extra"])
    return {
        "title": meta["title"],
        "date": meta["date"],
        "summary": meta["summary"],
        "tags": tags,
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
    site["videos"] = load_media(site.get("videos") or [], "videos", "watch", required_link=True)
    site["music"] = load_media(site.get("music") or [], "music", "listen", required_link=True)
    site["photos"] = load_photos(site.get("photos") or [])
    return site


def load_photos(raw):
    if not isinstance(raw, list):
        fail("site.json 的 photos 需要是数组")
    photos = []
    for item in raw:
        if not isinstance(item, dict):
            fail("photos 的条目需要是对象")
        for field in ("name", "src", "summary"):
            if not str(item.get(field) or "").strip():
                fail(f"照片条目缺少 {field}")
        src = item["src"].strip()
        if not PHOTO_SRC.match(src):
            fail(f"照片路径需要是 /images/<file> ：{src}")
        if not (SRC / src.lstrip("/")).is_file():
            fail(f"找不到照片 {src}")
        date = str(item.get("date") or "").strip()
        if date and not PHOTO_DATE.match(date):
            fail(f"照片日期需要是 YYYY 或 YYYY-MM-DD ：{date}")
        photos.append(
            {
                "name": item["name"].strip(),
                "src": src,
                "place": str(item.get("place") or "").strip(),
                "date": date,
                "summary": item["summary"].strip(),
            }
        )
    sort_newest(photos)
    for index, photo in enumerate(photos):
        photo["href"] = photo_page_href(index // PHOTO_PAGE_SIZE + 1)
    return photos


def load_media(raw, key, link_key, required_link):
    if not isinstance(raw, list):
        fail(f"site.json 的 {key} 需要是数组")
    entries = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            fail(f"{key} 的条目需要是对象")
        for field in ("slug", "name", "summary"):
            if not str(item.get(field) or "").strip():
                fail(f"{key} 条目缺少 {field}")
        slug = item["slug"].strip()
        if not SLUG.match(slug):
            fail(f"{key} 的 slug 不能作为 URL：{slug}")
        if slug in seen:
            fail(f"{key} 路径重复：/{key}/{slug}/")
        seen.add(slug)
        link = str(item.get(link_key) or "").strip()
        if required_link and not link:
            fail(f"{key} 条目缺少 {link_key}")
        if link and not link.startswith(("https://", "http://")):
            fail(f"{key} 的链接需要是 http(s)：{link}")
        if key == "music" and link and not APPLE_MUSIC.match(link):
            fail(f"音乐的 listen 需要是 https://music.apple.com/ 地址：{link}")
        date = str(item.get("date") or "").strip()
        if date and not PHOTO_DATE.match(date):
            fail(f"{key} 的 date 需要是 YYYY 或 YYYY-MM-DD ：{date}")
        tags = item.get("tags") or []
        if not isinstance(tags, list):
            fail(f"{key} 的 tags 需要是数组")
        parsed_tags = []
        for tag in tags:
            if not isinstance(tag, dict):
                fail(f"{key} 的 tag 需要包含 name 和 value")
            name = str(tag.get("name") or "").strip()
            value = str(tag.get("value") or "").strip()
            if not name or not value:
                fail(f"{key} 的 tag 需要包含 name 和 value")
            parsed_tags.append({"name": name, "value": value})
        entries.append(
            {
                "slug": slug,
                "name": item["name"].strip(),
                "summary": item["summary"].strip(),
                "link": link,
                "date": date,
                "tags": parsed_tags,
                "href": f"/{key}/{slug}/",
            }
        )
    return sort_newest(entries)


def text_tags(tags):
    if not tags:
        return ""
    items = [f'<li class="tag">{html.escape(tag)}</li>' for tag in tags]
    return '<ul class="tags">' + "".join(items) + "</ul>"


def pair_tags(tags):
    if not tags:
        return ""
    items = []
    for tag in tags:
        items.append(
            '<li class="tag">'
            f'<span class="tag-name">{html.escape(tag["name"])}</span>'
            f'{html.escape(tag["value"])}'
            "</li>"
        )
    return '<ul class="tags">' + "".join(items) + "</ul>"


def newest_key(item):
    value = item.get("date") or ""
    if len(value) == 4:
        value = value + "-01-01"
    return (bool(value), value)


def sort_newest(items):
    items.sort(key=newest_key, reverse=True)
    return items


def more_link(href, total):
    if total <= HOME_LIMIT:
        return ""
    return f'<p class="more"><a href="{html.escape(href)}">其余</a></p>\n'


def post_list(posts):
    if not posts:
        return '<p class="empty">还没有文章。</p>'
    items = []
    for post in posts:
        items.append(
            "<li>"
            f'<time datetime="{html.escape(post["date"])}">{html.escape(post["date"])}</time>'
            f'<a class="entry" href="{html.escape(post["href"])}">{html.escape(post["title"])}</a>'
            f'<p class="summary">{html.escape(post["summary"])}</p>'
            f"{text_tags(post['tags'])}"
            "</li>"
        )
    return '<ul class="list">\n' + "\n".join(items) + "\n</ul>"


def media_list(entries):
    items = []
    for entry in entries:
        date = ""
        if entry.get("date"):
            date = (
                f'<time datetime="{html.escape(entry["date"])}">'
                f'{html.escape(entry["date"])}</time>'
            )
        items.append(
            "<li>"
            f"{date}"
            f'<a class="entry" href="{html.escape(entry["href"])}">{html.escape(entry["name"])}</a>'
            f'<p class="summary">{html.escape(entry["summary"])}</p>'
            f"{pair_tags(entry['tags'])}"
            "</li>"
        )
    return '<ul class="list">\n' + "\n".join(items) + "\n</ul>"


def catalog_section(title, body, more="", catalog=True):
    kind = ' class="catalog"' if catalog else ""
    return f"<section{kind}>\n<h2>{html.escape(title)}</h2>\n{body}\n{more}</section>\n"


def still(src, alt, caption):
    return (
        '<figure class="still">\n'
        f'<img src="{html.escape(src)}" alt="{html.escape(alt)}">\n'
        f"<figcaption>{html.escape(caption)}</figcaption>\n"
        "</figure>\n"
    )


def photo_card(photo):
    rows = []
    if photo["place"]:
        rows.append(f"<div><dt>拍摄地</dt><dd>{html.escape(photo['place'])}</dd></div>")
    if photo["date"]:
        rows.append(
            "<div><dt>拍摄时间</dt>"
            f'<dd><time datetime="{html.escape(photo["date"])}">{html.escape(photo["date"])}</time></dd>'
            "</div>"
        )
    if photo["summary"]:
        rows.append(f"<div><dt>简介</dt><dd>{html.escape(photo['summary'])}</dd></div>")
    info = f'<dl class="photo-info">{"".join(rows)}</dl>' if rows else ""
    return (
        '<figure class="photo">\n'
        f"<h2>{html.escape(photo['name'])}</h2>\n"
        f'<img src="{html.escape(photo["src"])}" alt="{html.escape(photo["name"])}">\n'
        f"{info}\n"
        "</figure>"
    )


def photo_list(photos):
    if not photos:
        return '<p class="empty">还没有照片。</p>'
    items = []
    for index, photo in enumerate(photos):
        tags = []
        if photo["place"]:
            tags.append({"name": "拍摄地", "value": photo["place"]})
        if photo["date"]:
            tags.append({"name": "拍摄时间", "value": photo["date"]})
        items.append(
            "<li>"
            f'<a class="entry" href="{html.escape(photo["href"])}">{html.escape(photo["name"])}</a>'
            f'<p class="summary">{html.escape(photo["summary"])}</p>'
            f"{pair_tags(tags)}"
            "</li>"
        )
    return '<ul class="list">\n' + "\n".join(items) + "\n</ul>"


def photo_page_href(number):
    if number == 1:
        return "/photography/"
    return f"/photography/page/{number}/"


def photo_pager(page, pages):
    if pages <= 1:
        return ""
    links = []
    if page > 1:
        links.append(f'<a rel="prev" href="{photo_page_href(page - 1)}">上一页</a>')
    for number in range(1, pages + 1):
        current = ' aria-current="page"' if number == page else ""
        links.append(f'<a href="{photo_page_href(number)}"{current}>{number}</a>')
    if page < pages:
        links.append(f'<a rel="next" href="{photo_page_href(page + 1)}">下一页</a>')
    return '<nav class="pager" aria-label="分页">' + "".join(links) + "</nav>\n"


def photography_page(photos, page, pages):
    if not photos:
        return "<h1>摄影</h1>\n" + '<p class="empty">还没有照片。</p>'
    start = (page - 1) * PHOTO_PAGE_SIZE
    cards = "\n".join(photo_card(photo) for photo in photos[start : start + PHOTO_PAGE_SIZE])
    pager = photo_pager(page, pages)
    return f"<h1>摄影</h1>\n{pager}<div class=\"gallery\">\n{cards}\n</div>\n{pager}"


def projects_list(site):
    projects = site["projects"]
    if not projects:
        return '<p class="empty">还没有作品。</p>'
    items = []
    for project in projects:
        items.append(
            "<li>"
            f'<a class="entry" href="{html.escape(project["href"])}">'
            f"<span>{html.escape(project['name'])}</span>"
            '<span class="arrow" aria-hidden="true">→</span>'
            "</a>"
            f'<p class="summary">{html.escape(project["description"])}</p>'
            "</li>"
        )
    return '<ul class="list">\n' + "\n".join(items) + "\n</ul>"


def video_player(entry):
    matched = BVID.search(entry["link"] or "")
    if not matched:
        return ""
    src = (
        "https://player.bilibili.com/player.html"
        f"?bvid={matched.group(0)}&high_quality=1&autoplay=0"
    )
    title = html.escape(entry["name"])
    return (
        '<div class="player">'
        f'<iframe src="{html.escape(src)}" title="{title}" allowfullscreen></iframe>'
        "</div>"
    )


def music_player(entry):
    matched = APPLE_MUSIC.match(entry["link"] or "")
    if not matched:
        return ""
    src = "https://embed.music.apple.com" + matched.group(1)
    title = html.escape(entry["name"])
    return (
        '<div class="player player-audio">'
        f'<iframe src="{html.escape(src)}" title="{title}" '
        'allow="autoplay *; encrypted-media *; fullscreen *" '
        'sandbox="allow-forms allow-popups allow-same-origin allow-scripts '
        'allow-storage-access-by-user-activation allow-top-navigation-by-user-activation">'
        "</iframe>"
        "</div>"
    )


def media_page(entry, kind):
    if kind == "videos":
        player = video_player(entry)
    elif kind == "music":
        player = music_player(entry)
    else:
        player = ""
    return (
        '<article class="piece">\n'
        f"{player}\n"
        f"<h1>{html.escape(entry['name'])}</h1>\n"
        f"{pair_tags(entry['tags'])}\n"
        f'<p class="lede">{html.escape(entry["summary"])}</p>\n'
        "</article>"
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
            "photography_current": ' aria-current="page"' if current == "photography" else "",
            "blog_current": ' aria-current="page"' if current == "blog" else "",
            "videos_current": ' aria-current="page"' if current == "videos" else "",
            "music_current": ' aria-current="page"' if current == "music" else "",
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


def next_config_path(directory):
    for name in ("next.config.ts", "next.config.mjs", "next.config.js"):
        path = directory / name
        if path.is_file():
            return path
    return None


def is_next_export(directory):
    package_path = directory / "package.json"
    config = next_config_path(directory)
    if not package_path.is_file() or config is None:
        return False
    package = json.loads(package_path.read_text(encoding="utf-8"))
    dependencies = {}
    dependencies.update(package.get("dependencies") or {})
    dependencies.update(package.get("devDependencies") or {})
    if "next" not in dependencies:
        return False
    return "export" in config.read_text(encoding="utf-8")


def inject_base_path(text, base_path):
    if "basePath" in text:
        return text
    for needle in ("const nextConfig: NextConfig = {", "const nextConfig = {"):
        if needle in text:
            insertion = (
                needle
                + "\n"
                + f'  basePath: "{base_path}",\n'
                + f'  assetPrefix: "{base_path}",\n'
                + "  trailingSlash: true,"
            )
            return text.replace(needle, insertion, 1)
    fail("Next 配置里找不到 nextConfig，无法设置 basePath")


def prefix_public_paths(workspace):
    map_file = workspace / "components" / "china-map.tsx"
    if not map_file.is_file():
        return
    text = map_file.read_text(encoding="utf-8")
    old = 'fetch("/geo/china.json")'
    new = 'fetch(`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}/geo/china.json`)'
    if old not in text:
        return
    map_file.write_text(text.replace(old, new, 1), encoding="utf-8")


def run_command(command, cwd, env=None):
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=cwd, env=env)
    if completed.returncode != 0:
        fail(f"命令失败：{' '.join(command)}")


def build_next_export(directory, base_path, destination):
    config = next_config_path(directory)
    with tempfile.TemporaryDirectory(prefix="pages-project-") as temporary:
        workspace = Path(temporary) / "app"
        shutil.copytree(
            directory,
            workspace,
            ignore=shutil.ignore_patterns(".git", "node_modules", ".next", "out"),
        )
        config_copy = workspace / config.name
        config_copy.write_text(
            inject_base_path(config_copy.read_text(encoding="utf-8"), base_path),
            encoding="utf-8",
        )
        prefix_public_paths(workspace)
        run_command(["npm", "ci"], workspace)
        env = os.environ.copy()
        env["NEXT_PUBLIC_BASE_PATH"] = base_path
        run_command(["npm", "run", "build"], workspace, env)
        output = workspace / "out"
        if not (output / "index.html").is_file():
            fail(f"{directory.name} 的静态导出里没有 index.html")
        shutil.copytree(output, destination)


def publish_project(name, directory):
    destination = DIST / "projects" / name
    if is_next_export(directory):
        build_next_export(directory, f"/projects/{name}", destination)
        return
    if (directory / "index.html").is_file() and has_site_files(directory):
        shutil.copytree(directory, destination, ignore=shutil.ignore_patterns(".*"))
        return
    fail(f"项目 {name} 需要放在 projects/{name}/，并且包含 index.html")


def copy_projects(site):
    listed = set()
    for project in site["projects"]:
        name = PROJECT_HREF.match(project["href"]).group(1)
        directory = PROJECTS_DIR / name
        if not directory.is_dir():
            fail(f"项目 {name} 需要放在 projects/{name}/")
        publish_project(name, directory)
        listed.add(name)

    if not PROJECTS_DIR.exists():
        return
    for child in PROJECTS_DIR.iterdir():
        if not child.is_dir() or child.name.startswith(".") or child.name in listed:
            continue
        if (child / "index.html").is_file():
            shutil.copytree(
                child,
                DIST / "projects" / child.name,
                ignore=shutil.ignore_patterns(".*"),
            )


def build():
    site = load_site()
    posts = load_posts()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    photos = site["photos"]
    articles = post_list(posts)
    videos = media_list(site["videos"]) if site["videos"] else '<p class="empty">还没有视频。</p>'
    music = media_list(site["music"]) if site["music"] else '<p class="empty">还没有收入音乐。</p>'
    home_articles = post_list(posts[:HOME_LIMIT]) or articles
    home_videos = media_list(site["videos"][:HOME_LIMIT]) if site["videos"] else videos
    home_music = media_list(site["music"][:HOME_LIMIT]) if site["music"] else music
    home_photos = photo_list(photos[:HOME_LIMIT])
    home = (
        still("/images/sea.jpg", "雾中平静的海面", "海雾")
        + f"<h1>{html.escape(site['title'])}</h1>\n"
        + f"<p class=\"lede\">{html.escape(site['description'])}</p>\n"
        + catalog_section("文章", home_articles, more_link("/blog/", len(posts)), catalog=False)
        + catalog_section("视频", home_videos, more_link("/videos/", len(site["videos"])))
        + catalog_section("音乐", home_music, more_link("/music/", len(site["music"])))
        + catalog_section("摄影", home_photos, more_link("/photography/", len(photos)))
    )
    page_count = max(1, (len(photos) + PHOTO_PAGE_SIZE - 1) // PHOTO_PAGE_SIZE)
    write_page("index.html", render_page(site, site["title"], home, "home"))
    for page in range(1, page_count + 1):
        relative = "photography/index.html" if page == 1 else f"photography/page/{page}/index.html"
        write_page(
            relative,
            render_page(site, "摄影", photography_page(photos, page, page_count), "photography"),
        )
    write_page("blog/index.html", render_page(site, "文章", f"<h1>文章</h1>\n{articles}", "blog"))
    write_page("videos/index.html", render_page(site, "视频", f"<h1>视频</h1>\n{videos}", "videos"))
    write_page("music/index.html", render_page(site, "音乐", f"<h1>音乐</h1>\n{music}", "music"))

    for entry in site["videos"]:
        write_page(
            f"videos/{entry['slug']}/index.html",
            render_page(site, entry["name"], media_page(entry, "videos"), "videos"),
        )
    for entry in site["music"]:
        write_page(
            f"music/{entry['slug']}/index.html",
            render_page(site, entry["name"], media_page(entry, "music"), "music"),
        )

    for post in posts:
        article = (
            "<article>\n"
            f"<h1>{html.escape(post['title'])}</h1>\n"
            f"<time datetime=\"{html.escape(post['date'])}\">{html.escape(post['date'])}</time>\n"
            f"{text_tags(post['tags'])}\n"
            f"<p class=\"lede\">{html.escape(post['summary'])}</p>\n"
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
        '<p><a class="back" href="/">返回首页</a></p>'
    )
    write_page("404.html", render_page(site, "页面不存在", missing, ""))
    shutil.copyfile(SRC / "style.css", DIST / "style.css")
    images = SRC / "images"
    if images.is_dir():
        shutil.copytree(images, DIST / "images")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    copy_projects(site)


if __name__ == "__main__":
    build()
