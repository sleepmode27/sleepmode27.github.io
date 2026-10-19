# sleepmode27.github.io

个人博客首页。导航和栏目标题是 photography、videos、music、articles，对应摄影、视频、音乐、文章。首页按这个顺序排列。

文章放在 `content/posts`。摄影、视频和音乐写在 `site.json`。其他网页项目挂到 `projects/<name>`，发布后从对应 URL 直接访问。

站点由 GitHub Actions 构建。仓库需要公开，Pages 的构建来源选择 GitHub Actions。改完后提交并推送到 `main`，Actions 会重新发布。

本地预览：

```bash
pip install markdown
python3 scripts/build.py
python3 -m http.server -d dist
```

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

`title`、`date`、`summary` 都要写。`date` 使用 `YYYY-MM-DD`。`tags` 用逗号分隔，可以不写。列表和文章页都会显示简介；写了标签也会显示。

## 增加一张照片

把图片放进 `src/images/`，再在 `site.json` 的 `photos` 里加一条：

```json
{
  "name": "海雾",
  "src": "/images/sea.jpg",
  "place": "海上",
  "date": "",
  "summary": "雾把天和海接在一起，只剩一层浅色的水面。"
}
```

`name`、`src`、`summary` 必填。`src` 写成 `/images/<文件名>`，文件要真实存在。`place` 和 `date` 可以省略。`date` 用 `YYYY` 或 `YYYY-MM-DD`；没有可靠的拍摄时间就留空，页面上不会出现「拍摄时间」。

摄影、文章、视频和音乐都按日期从新到旧排列，栏目页每页 6 条。第一页是栏目地址本身，例如 `/photography/`、`/blog/`、`/videos/`、`/music/`。第 7 条起在对应的 `/page/2/`。分页只出现在内容下方靠右。不超过 7 页时显示全部页码；再多就只留当前页附近、第 1 页和最后一页，中间用省略号。不足 6 条时不显示分页。没有日期的条目排在最后。首页每个栏目只放最新 3 条；超过 3 条时，下面有「全部文章」「全部视频」「全部音乐」或「全部摄影」，点进去就是对应栏目页。首页摄影是三张横图，标题和简介在图下；文章、视频和音乐仍是文字列表。首页顶部的大图仍是 `/images/sea.jpg`。

## 增加一个视频

在 `site.json` 的 `videos` 里加一条。`watch` 填哔哩哔哩视频地址。

```json
{
  "slug": "guang",
  "name": "光",
  "summary": "一段简介",
  "date": "2025-02-11",
  "watch": "https://www.bilibili.com/video/BV1RPNqeYEeD/",
  "tags": [
    {"name": "音乐人", "value": "haruka nakamura"},
    {"name": "流派", "value": "现代古典"},
    {"name": "合奏", "value": "CANTUS"}
  ]
}
```

`slug` 用英文和数字，地址是 `/videos/guang/`。`date` 可以不写，格式与照片相同。写了以后首页会按日期取最新 3 条，列表里也会显示。列表不放播放器，点进详情后才出现，播放器下方有原视频链接。

## 增加一首音乐

在 `site.json` 的 `music` 里加一条。`listen` 填网易云歌曲页，形如 `https://music.163.com/song?id=<数字>`。详情页嵌入网易云播放条，下面再放一条「在网易云音乐收听」。

```json
{
  "slug": "guang",
  "name": "Light song",
  "summary": "一段简介",
  "date": "2024-06-28",
  "listen": "https://music.163.com/song?id=2600522744",
  "tags": [
    {"name": "音乐人", "value": "中村遥"}
  ]
}
```

地址是 `/music/guang/`。`date` 可以不写。列表不放播放器。

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

发布后从 `https://sleepmode27.github.io/projects/<name>/` 访问。首页不再单列 works。

子项目更新后，在本仓库更新指针再推送：

```bash
git submodule update --remote projects/<name>
git add projects/<name>
git commit -m "update <name>"
git push
```

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
