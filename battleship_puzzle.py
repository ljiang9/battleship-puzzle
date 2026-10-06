#!/usr/bin/env python3
"""Battleships solitaire（舰队谜题）生成器与求解器。

规则：把一支舰队放进 n×n 网格，舰船之间不接触（含对角线）。
每行/每列的舰船格数作为线索给出，部分格子预先揭示为船/水。

纯标准库：argparse / random / sys。
"""
from __future__ import annotations

import argparse
import random
import sys

# 每种尺寸的舰队：数字 = 船的长度
FLEETS = {
    10: [4, 3, 3, 2, 2, 2, 1, 1, 1, 1],
    8: [3, 2, 2, 1, 1, 1],
    6: [3, 2, 1, 1],
}

NEIGHBORS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


# ---------------------------------------------------------------- 生成器

def _touches(cells, occupied):
    """cells（同一条船）是否与 occupied 中的船格 8-邻接。"""
    own = set(cells)
    for r, c in cells:
        for dr, dc in NEIGHBORS:
            nb = (r + dr, c + dc)
            if nb in occupied and nb not in own:
                return True
    return False


def random_layout(n, fleet, rng):
    """随机放出一个合法舰队布局。返回每条船的格子列表，失败返回 None。"""
    ships = sorted(fleet, reverse=True)
    occupied = set()
    placed = []
    for length in ships:
        cands = []
        for r in range(n):
            for c in range(n):
                for horiz in (True, False):
                    if length == 1 and not horiz:
                        continue
                    cells = [(r, c + i) if horiz else (r + i, c) for i in range(length)]
                    if any(not (0 <= x < n and 0 <= y < n) for x, y in cells):
                        continue
                    if set(cells) & occupied:
                        continue
                    if _touches(cells, occupied):
                        continue
                    cands.append(cells)
        if not cands:
            return None
        cells = rng.choice(cands)
        placed.append(cells)
        occupied |= set(cells)
    return placed


def make_puzzle(n, seed=None, reveal=0.3):
    """生成一道谜题。返回 dict：n / fleet / rows / cols / givens / solution。"""
    rng = random.Random(seed)
    fleet = FLEETS[n]
    layout = None
    for _ in range(500):
        layout = random_layout(n, fleet, rng)
        if layout is not None:
            break
    if layout is None:
        raise RuntimeError("生成布局失败，请换 seed 重试")
    ship = [[False] * n for _ in range(n)]
    for cells in layout:
        for r, c in cells:
            ship[r][c] = True
    rows = [sum(row) for row in ship]
    cols = [sum(ship[r][c] for r in range(n)) for c in range(n)]
    givens = [["."] * n for _ in range(n)]
    for r in range(n):
        for c in range(n):
            if rng.random() < reveal:
                givens[r][c] = "#" if ship[r][c] else "~"
    return {"n": n, "fleet": fleet, "rows": rows, "cols": cols,
            "givens": givens, "solution": layout}


# ---------------------------------------------------------------- 求解器

class TooHard(Exception):
    pass


def solve_puzzle(n, fleet, givens, rows, cols, max_nodes=2_000_000):
    """回溯求解。返回船格集合的列表（每条船一个集合），无解返回 None。"""
    grid = [[0] * n for _ in range(n)]  # 0 未知，1 船，-1 水
    given_ship = set()
    for r in range(n):
        for c in range(n):
            g = givens[r][c]
            if g == "#":
                grid[r][c] = 1
                given_ship.add((r, c))
            elif g == "~":
                grid[r][c] = -1
    rem_row = rows[:]
    rem_col = cols[:]
    for r, c in given_ship:
        rem_row[r] -= 1
        rem_col[c] -= 1
    if any(v < 0 for v in rem_row) or any(v < 0 for v in rem_col):
        return None

    # 预计算每种船长的所有几何摆放（与棋盘状态无关）
    placements = {}
    for length in set(fleet):
        pls = []
        for r in range(n):
            for c in range(n):
                for horiz in (True, False):
                    if length == 1 and not horiz:
                        continue
                    cells = tuple((r, c + i) if horiz else (r + i, c)
                                  for i in range(length))
                    if all(0 <= x < n and 0 <= y < n for x, y in cells):
                        pls.append(cells)
        placements[length] = pls

    ships = sorted(fleet, reverse=True)
    placed = []          # 每条船的格子列表
    trail = []           # 撤销栈：(r, c, old_value)
    nodes = [0]

    def valid_placement(cells):
        cellset = set(cells)
        need_row = {}
        need_col = {}
        for x, y in cells:
            if grid[x][y] == -1:
                return None
            if grid[x][y] != 1:
                need_row[x] = need_row.get(x, 0) + 1
                need_col[y] = need_col.get(y, 0) + 1
            for dx, dy in NEIGHBORS:
                nx, ny = x + dx, y + dy
                if (0 <= nx < n and 0 <= ny < n and grid[nx][ny] == 1
                        and (nx, ny) not in cellset):
                    return None
        for x, k in need_row.items():
            if rem_row[x] < k:
                return None
        for y, k in need_col.items():
            if rem_col[y] < k:
                return None
        return cellset

    def place(cells, cellset):
        mark = len(trail)
        for x, y in cells:
            if grid[x][y] == 0:
                trail.append((x, y, 0))
                grid[x][y] = 1
                rem_row[x] -= 1
                rem_col[y] -= 1
            for dx, dy in NEIGHBORS:
                nx, ny = x + dx, y + dy
                if (nx, ny) in cellset:
                    continue
                if 0 <= nx < n and 0 <= ny < n and grid[nx][ny] == 0:
                    trail.append((nx, ny, 0))
                    grid[nx][ny] = -1
        placed.append(cells)
        return mark

    def unplace(mark):
        placed.pop()
        while len(trail) > mark:
            x, y, old = trail.pop()
            if grid[x][y] == 1 and old == 0:
                rem_row[x] += 1
                rem_col[y] += 1
            grid[x][y] = old

    def rowcol_prunable():
        # 行列可用格剪枝：每行非水格数必须 >= 剩余船格数
        for r in range(n):
            if rem_row[r] < 0:
                return True
            if sum(1 for c in range(n) if grid[r][c] != -1) < rem_row[r]:
                return True
        for c in range(n):
            if rem_col[c] < 0:
                return True
            if sum(1 for r in range(n) if grid[r][c] != -1) < rem_col[c]:
                return True
        return False

    sys.setrecursionlimit(10000)

    def dfs(todo):
        nodes[0] += 1
        if nodes[0] > max_nodes:
            raise TooHard()
        if not todo:
            covered = set()
            for cells in placed:
                covered |= set(cells)
            if not given_ship <= covered:
                return None
            if any(rem_row) or any(rem_col):
                return None
            return [set(c) for c in placed]
        # 每艘剩余船算一次候选（只与船长和棋盘状态有关）
        per_ship = []  # (todo下标, [(cells, cellset)])
        for i, length in enumerate(todo):
            c = []
            for cells in placements[length]:
                cs = valid_placement(cells)
                if cs is not None:
                    c.append((cells, cs))
            if not c:
                return None
            per_ship.append((i, c))
        if rowcol_prunable():
            return None
        by_len = {}  # 船长 -> [(todo下标, 候选)]
        for i, c in per_ship:
            by_len.setdefault(todo[i], []).append((i, c))
        covered = set()
        for cells in placed:
            covered |= set(cells)
        uncovered = given_ship - covered
        if uncovered:
            # 以"未覆盖的预设船格"为变量：选覆盖选项最少的格子分支
            best_opts = None
            for cell in uncovered:
                opts = []  # (船长, todo下标代表, 覆盖该格的摆放)
                for length, lst in by_len.items():
                    i0, c0 = lst[0]  # 同长度船完全对称，取代表即可
                    cov = [(cells, cs) for cells, cs in c0 if cell in cs]
                    if cov:
                        opts.append((i0, cov))
                if not opts:
                    return None
                total = sum(len(cov) for _, cov in opts)
                if best_opts is None or total < sum(len(c) for _, c in best_opts):
                    best_opts = opts
                    if total == 1:
                        break
            for i0, cov in best_opts:
                rest = todo[:i0] + todo[i0 + 1:]
                for cells, cellset in cov:
                    mark = place(cells, cellset)
                    res = dfs(rest)
                    if res is not None:
                        return res
                    unplace(mark)
            return None
        # 无未覆盖预设：MRV 选候选最少的船
        i, c = min(per_ship, key=lambda t: len(t[1]))
        rest = todo[:i] + todo[i + 1:]
        for cells, cellset in c:
            mark = place(cells, cellset)
            res = dfs(rest)
            if res is not None:
                return res
            unplace(mark)
        return None

    try:
        return dfs(ships)
    except TooHard:
        return None


def check_solution(n, fleet, givens, rows, cols, ships):
    """校验解合法。返回 (ok, message)。"""
    if ships is None:
        return False, "无解"
    if sorted(len(s) for s in ships) != sorted(fleet):
        return False, "船队组成不对"
    all_cells = set()
    for s in ships:
        if all_cells & s:
            return False, "船重叠"
        all_cells |= s
    # 不接触
    cells_list = list(all_cells)
    ship_of = {}
    for i, s in enumerate(ships):
        for cell in s:
            ship_of[cell] = i
    for r, c in cells_list:
        for dr, dc in NEIGHBORS:
            nb = (r + dr, c + dc)
            if nb in all_cells and ship_of[nb] != ship_of[(r, c)]:
                return False, "船只接触"
    # 行列计数
    for r in range(n):
        if sum(1 for c in range(n) if (r, c) in all_cells) != rows[r]:
            return False, f"第 {r} 行计数不符"
    for c in range(n):
        if sum(1 for r in range(n) if (r, c) in all_cells) != cols[c]:
            return False, f"第 {c} 列计数不符"
    # 预设
    for r in range(n):
        for c in range(n):
            g = givens[r][c]
            if g == "#" and (r, c) not in all_cells:
                return False, "预设船格未被覆盖"
            if g == "~" and (r, c) in all_cells:
                return False, "预设水格被占用"
    return True, "合法"


# ---------------------------------------------------------------- 文本格式

def render(n, rows, cols, givens, ships=None):
    """渲染谜题（ships 非空时同时显示解）。"""
    lines = []
    head = "    " + " ".join(f"{c:2d}" for c in cols)
    lines.append(head)
    lines.append("   +" + "---" * n + "+")
    for r in range(n):
        row = []
        for c in range(n):
            if ships is not None:
                row.append("#" if any((r, c) in s for s in ships) else ".")
            else:
                row.append(givens[r][c])
        lines.append(f"{rows[r]:2d} |" + " ".join(f"{x:2s}" for x in row) + "|")
    lines.append("   +" + "---" * n + "+")
    return "\n".join(lines)


def save_puzzle(path, p):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{p['n']}\n")
        f.write(" ".join(map(str, p["rows"])) + "\n")
        f.write(" ".join(map(str, p["cols"])) + "\n")
        for row in p["givens"]:
            f.write("".join(row) + "\n")


def load_puzzle(path):
    with open(path, encoding="utf-8") as f:
        ls = [ln.rstrip("\n") for ln in f if ln.strip() != ""]
    n = int(ls[0])
    rows = list(map(int, ls[1].split()))
    cols = list(map(int, ls[2].split()))
    givens = [list(ls[3 + r][:n]) for r in range(n)]
    fleet = FLEETS[n]
    return n, fleet, givens, rows, cols


# ---------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="battleship-puzzle",
        description="舰队谜题（Battleships solitaire）生成器与求解器")
    ap.add_argument("--size", type=int, choices=[6, 8, 10], default=8,
                    help="棋盘尺寸（默认 8）")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--reveal", type=float, default=0.3,
                    help="预设格子揭示比例（默认 0.3）")
    ap.add_argument("--save", metavar="FILE", help="把生成的谜题存成文本文件")
    ap.add_argument("--solution", action="store_true", help="同时打印完整解")
    ap.add_argument("--load", metavar="FILE", help="从文件读入谜题而不是生成")
    ap.add_argument("--solve", action="store_true", help="求解（默认只生成谜题）")
    ap.add_argument("--max-nodes", type=int, default=2_000_000,
                    help="求解搜索节点上限（默认 2000000）")
    args = ap.parse_args(argv)

    if args.load:
        n, fleet, givens, rows, cols = load_puzzle(args.load)
    else:
        p = make_puzzle(args.size, seed=args.seed, reveal=args.reveal)
        n, fleet, givens, rows, cols = p["n"], p["fleet"], p["givens"], p["rows"], p["cols"]
        if args.save:
            save_puzzle(args.save, p)
            print(f"谜题已保存到 {args.save}")

    print(f"舰队谜题 {n}x{n}，舰队：{' '.join(map(str, sorted(fleet, reverse=True)))}")
    print("图例：# 船（预设）  ~ 水（预设）  . 未知；上方/左侧数字为列/行船格数")
    print(render(n, rows, cols, givens))

    if args.solve or args.solution or args.load:
        ships = solve_puzzle(n, fleet, givens, rows, cols, max_nodes=args.max_nodes)
        if ships is None:
            print("求解失败：无解，或搜索超出节点上限。")
            return 1
        ok, msg = check_solution(n, fleet, givens, rows, cols, ships)
        print(f"\n求解完成：{msg}")
        print(render(n, rows, cols, givens, ships))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
