#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个人频道筛选器
根据 my_channels.txt（即 demo.txt 格式的频道清单），
从仓库内的 live.txt、live_lite.txt、live_platforms.m3u、live.m3u 中
筛选出想要的频道，生成两个订阅文件：
  - my.m3u  （M3U 格式，适合 TiviMate / DIPTV / Perfect Player 等）
  - my.txt  （TXT 格式，适合 TVBox / 影视仓 等）

用法：python filter.py
"""

import os
import re
import sys

# ================== 配置区（可按需修改） ==================
# 你的频道清单文件（分组格式：xxx,#genre#）
CHANNEL_FILE = "my_channels.txt"

# 参与筛选的直播源文件（都在仓库根目录，由原项目的 Actions 自动更新）
SOURCES_TXT = ["live.txt", "live_lite.txt"]
SOURCES_M3U = ["live_platforms.m3u", "live.m3u"]

# 输出文件
OUT_M3U = "my.m3u"
OUT_TXT = "my.txt"

# 跳过这些干扰频道（原项目里的“列表更新时间”等测试条目）
SKIP_NAMES = {"更新时间", "列表更新时间", "4k60psdr-h264-aac测试", "4k60phlg-hevc-eac3测试"}
# ==========================================================


def norm(name: str) -> str:
    """频道名标准化：去空格、横杠、下划线，统一小写，用于模糊匹配。"""
    s = name.strip().lower()
    s = re.sub(r"[\s\-_—–·・.。]", "", s)
    return s


def parse_channel_file(path: str):
    """解析频道清单，返回 (分组顺序列表, [(组名, 频道名), ...])"""
    groups = []
    group_order = []
    current = "未分组"
    if not os.path.exists(path):
        sys.exit(f"❌ 找不到频道清单 {path}")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.endswith("#genre#"):
                # 支持 “组名,#genre#” 和 “emoji,组名#genre#” 两种写法
                current = line[: line.index("#genre#")].rstrip(",").strip()
                current = current.replace(",", " ").replace("，", " ").strip() or "未分组"
                if current not in group_order:
                    group_order.append(current)
            else:
                # 清单里每行可能写作 “频道名” 或 “频道名,备注”
                name = line.split(",")[0].strip()
                if name:
                    groups.append((current, name))
    return group_order, groups


def parse_txt_source(path: str):
    """解析 TXT 直播源，返回 [(频道名, url), ...]"""
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.endswith("#genre#"):
                continue
            if "," in line:
                name, url = line.rsplit(",", 1)
                name, url = name.strip(), url.strip()
                if name and url.startswith("http"):
                    entries.append((name, url))
    return entries


def parse_m3u_source(path: str):
    """解析 M3U 直播源，返回 [(频道名, url, extinf整行), ...]"""
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path, encoding="utf-8", errors="ignore") as f:
        lines = [l.rstrip("\n") for l in f]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            url = lines[i + 1].strip() if i + 1 < len(lines) else ""
            # 频道显示名 = EXTINF 行最后一个逗号之后的内容
            name = line.rsplit(",", 1)[-1].strip()
            if name and url.startswith("http"):
                entries.append((name, url, line))
            i += 2
        else:
            i += 1
    return entries


def main():
    group_order, wanted = parse_channel_file(CHANNEL_FILE)
    # 频道名 -> 想要的分组（同一个频道只归入第一次出现的分组）
    want_map = {}
    for group, name in wanted:
        want_map.setdefault(norm(name), group)

    # 读取所有源
    txt_entries = []  # (name, url)
    m3u_entries = []  # (name, url, extinf)
    for src in SOURCES_TXT:
        txt_entries += parse_txt_source(src)
    for src in SOURCES_M3U:
        m3u_entries += parse_m3u_source(src)
    print(f"📥 已读取源文件：TXT {len(txt_entries)} 条，M3U {len(m3u_entries)} 条")

    # 按频道名归集所有可用链接（M3U 源优先，可保留台标），并按 (频道, url) 去重
    seen = set()
    by_channel = {}  # 标准化频道名 -> [(显示名, url, logo)]
    found_names = set()

    def add_entry(name, url, logo):
        key = (norm(name), url)
        if key in seen:
            return
        seen.add(key)
        by_channel.setdefault(norm(name), []).append((name, url, logo))
        found_names.add(norm(name))

    for name, url, extinf in m3u_entries:  # M3U 源（保留台标）
        if norm(name) in want_map and norm(name) not in SKIP_NAMES:
            logo_m = re.search(r'tvg-logo="([^"]+)"', extinf)
            add_entry(name, url, logo_m.group(1) if logo_m else None)

    for name, url in txt_entries:  # 再补充 TXT 源（通常无台标）
        if norm(name) in want_map and norm(name) not in SKIP_NAMES:
            add_entry(name, url, None)

    # 按清单顺序组织输出：(组名, 频道名, [(显示名, url, logo)])
    ordered = []
    for group, name in wanted:
        n = norm(name)
        items = by_channel.get(n, [])
        ordered.append((group, name, items))

    # 写出 TXT
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        total = 0
        for g in group_order:
            lines = [(name, url) for gg, name, items in ordered if gg == g for name, url, _ in items]
            if not lines:
                continue
            f.write(f"{g},#genre#\n")
            for name, url in lines:
                f.write(f"{name},{url}\n")
                total += 1
            f.write("\n")

    # 写出 M3U
    with open(OUT_M3U, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for g in group_order:
            items = [(name, url, logo) for gg, name, lst in ordered if gg == g for name, url, logo in lst]
            if not items:
                continue
            for name, url, logo in items:
                logo_part = f' tvg-logo="{logo}"' if logo else ""
                f.write(f'#EXTINF:-1 tvg-name="{name}"{logo_part} group-title="{g}",{name}\n')
                f.write(f"{url}\n")

    # 统计报告
    missing = [n for n, g in want_map.items() if n not in found_names]
    print(f"✅ 筛选完成：共输出 {total} 条频道链接")
    for g in group_order:
        chans = len({norm(name) for gg, name, _ in ordered if gg == g and by_channel.get(norm(name))})
        links = sum(len(items) for gg, name, items in ordered if gg == g)
        if links:
            print(f"   - {g}: {chans} 个频道 / {links} 条链接")
    if missing:
        print(f"⚠️ 有 {len(missing)} 个频道本次未在直播源中找到（已自动跳过，源更新后可能恢复）：")
        print("   " + "、".join(missing))


if __name__ == "__main__":
    main()
