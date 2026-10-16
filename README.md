# sleepmode27.github.io

个人博客首页。文章放在 `content/posts`，其他静态网页项目挂到 `projects/<name>`，发布后从对应 URL 直接访问。

站点由 GitHub Actions 构建。仓库需要公开，Pages 的构建来源选择 GitHub Actions。

## 新增一篇文章

在 `content/posts` 新建 Markdown 文件，文件名用日期开头：

```
content/posts/2026-10-16-hello.md
```

对应地址是 `/blog/hello/`。

```markdown
---
title: 开始
date: 2026-10-16
summary: 一句话介绍
tags: 随笔, 记录
---

正文。
```

`title`、`date`、`summary` 都要写。`date` 使用 `YYYY-MM-DD`。`tags` 用逗号分隔，列表和文章页都会显示简介和这些标签。提交并推送到 `main` 后，Actions 会重新发布。

## 视频、音乐和 works

`site.json` 里分开写 `videos`、`music` 和 `projects`。

视频页只放标题、简介和标签，不嵌入播放器。标题在详情页链到外部观看地址。

```json
{
  "slug": "guang",
  "name": "光",
  "summary": "一段简介",
  "watch": "https://www.bilibili.com/video/BV1RPNqeYEeD/",
  "tags": [
    {"name": "musician", "value": "haruka nakamura"},
    {"name": "流派", "value": "现代古典"}
  ]
}
```

地址是 `/videos/guang/`。音乐用同样的字段，外链键名是 `listen`，地址在 `/music/<slug>/`。`projects` 出现在 `/works/`，用来放开发项目。

## 以后把文章拆成独立仓库

新仓库的根目录保持 `posts/` 这一层。在本仓库执行：

```bash
git submodule add https://github.com/sleepmode27/blog-posts.git content
```

构建脚本仍然读取 `content/posts`，文章地址不用改。子仓库使用 HTTPS 地址，Actions 才能拉取公开仓库。

文章仓库更新后，在本仓库更新指针再推送，站点才会变：

```bash
git submodule update --remote content
git add content
git commit -m "update posts"
git push
```

## 挂载一个网页子项目

子项目仓库的根目录需要能直接当网站打开，并且包含 `index.html`。样式和脚本使用相对路径，例如 `./style.css`。Next 静态导出项目可以直接挂源码仓库，站点构建时会安装依赖，把 `basePath` 设为 `/projects/<name>` 并导出静态文件。

```bash
git submodule add https://github.com/sleepmode27/<repo>.git projects/<name>
```

然后在 `site.json` 的 `projects` 里加上名称、介绍和链接：

```json
{
  "name": "项目名",
  "description": "一句话介绍",
  "href": "/projects/<name>/"
}
```

发布后从 `https://sleepmode27.github.io/projects/<name>/` 访问。

子项目更新后，在本仓库更新指针再推送：

```bash
git submodule update --remote projects/<name>
git add projects/<name>
git commit -m "update <name>"
git push
```

本地预览：

```bash
pip install markdown
python3 scripts/build.py
python3 -m http.server -d dist
```
