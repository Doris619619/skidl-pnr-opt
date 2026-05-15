# 更新记录（human_readable 布局 / 走线稳定化）

**日期**：2026-05-13  
**范围**：原理图自动布局与走线（`place.py`、`route.py`），默认行为不变。

---

## 目的

- 在可选模式下让生成的 `.kicad_sch` 更接近工程师手工排版习惯（主控居中、电源/去耦分区、接口左右等启发式）。
- 减少随机性，使同一输入多次生成坐标与走线更稳定。
- 遵循小步、保守、可回滚：不引入新依赖、不重写整个 placer/router。

---

## 涉及文件

| 文件 | 说明 |
|------|------|
| `src/skidl/schematics/place.py` | 主要改动：`human_readable` 分支、工具函数、auto_stub 微调、默认 seed |
| `src/skidl/schematics/route.py` | 轻量改动：稳定 `global_router` 起点、`remove_jogs` 顺序、`humanize_wires`、默认 seed |

---

## 如何启用

在调用 `place` / `route` 时传入可选参数：

```python
node.place(..., human_readable=True)
node.route(..., human_readable=True)
```

- **`human_readable=False`（默认）**：保持原有逻辑与分支，与改动前一致。
- **`human_readable=True` 且未传 `seed`**：内部使用固定默认种子 `0`，便于回归与对比输出。

---

## `place.py` 变更摘要

### 新增（`Placer` 内小工具，非新 public API）

- `_part_ref_key(part)`：按 `ref` / `name` / `value` 稳定排序键。
- `_net_names_of(part)`：安全返回器件所连 net 名称集合。
- `_is_power_net_name(name)`：电源/地 net 名启发式。
- `_classify_part_role(part)`：`power` / `decoupling` / `ic` / `connector` / `passive` / `other`。
- `_find_main_part(parts)`：优先 pin 数最多的 IC，否则连接度最高，tie 用稳定排序。
- `_place_row(...)`：按 `place_bbox` 与 `GRID` / `BLK_INT_PAD` 行摆放。

### `place_connected_parts_rowbased`

- **`human_readable=True`**：按主器件 + 角色分区布局；末尾保守去重叠 + `snap_to_grid`。
- **`human_readable=False`**：仍为原 BFS + 行打包逻辑。

### `place_floating_parts`

- **`human_readable=True`**：按 role 分桶、`value/ref` 稳定排序，被动件按 R/C/L 等分行，不依赖随机初始布局。
- 默认路径不变（含大数量浮动件 + `auto_stub` 的 sqrt grid 等）。

### `place_blocks`

- 当 block 数量超过阈值且 **`human_readable=True`**：连通块居中行、浮动块下方、子 sheet 右侧，按 `tag`、面积、`ref` 稳定排序。
- 默认仍为原 sqrt grid + 力导向等。

### `_auto_stub_large_groups`

- **`human_readable=True` 且 `auto_stub=True`**：更倾向对电源类 net 与候选链 net 排序后做有限次数 stub，避免“全图标签化”；默认分支保持原等步长切割逻辑。

### `place()` 随机种子

- `human_readable=True` 且用户未传 `seed` 时，使用固定种子 `0`。

---

## `route.py` 变更摘要

### `route()`

- 与 place 一致：`human_readable=True` 且无 `seed` 时默认 `seed=0`。
- 将本次 `options` 暂存于 `node._route_options`，供内部读取；正常结束或 `RoutingFailure` 时清理。

### `global_router()`

- **`human_readable=True`**：`start_face` 按 track 坐标、beg/end、pin/terminal 数量等可比较键排序后取第一个，替代 `random.choice`。
- 默认仍为随机选择。

### `cleanup_wires()` 内 `remove_jogs()`

- **`human_readable=True`**：不对 segments / `p2s` 做 `shuffle`，改为稳定排序顺序。
- **`human_readable=True`**：在通用 `cleanup_wires` 流程末尾调用 `humanize_wires()`。

### `humanize_wires()`（新增）

- 仅在 human 模式、且 `cleanup_wires` 之后执行。
- 保守操作：去零长段、稳定排序、对极短且弱连接的 stub 做 trim；不改动电气连接语义；避免穿越器件 bbox 的激进简化未做。

---

## 验收与自检

- `python -m compileall src/skidl/schematics/place.py src/skidl/schematics/route.py` 通过。
- `import skidl.schematics.place`、`import skidl.schematics.route` 通过（环境缺 KiCad 符号路径时可能有既有 WARNING，与本次改动无关）。

---

## 回滚说明

- 不传 `human_readable` 或显式 `human_readable=False` 即可恢复改动前行为。
- 若需完全撤销代码：仅回退上述两个文件在本记录日期附近的提交即可。

---

## 2026-05-14 更新：human 路由崩溃修复 + 网表仓库默认输出目录

### 1. `route.py` — `SwitchBox.coalesce` KeyError

- **现象**：`human_readable=True` 时，部分电路在 `create_switchboxes` → `coalesce` 中执行 `(box_face.switchboxes - {box}).pop()` 会因邻接集为空触发 **`KeyError: 'pop from an empty set'`**（例如 `examples/5micro_3`）。
- **原因**：布局/track 切分退化时，某 face 上记录的 `switchboxes` 可能未包含预期邻盒，空集仍被 `pop()`。
- **修复**：先判断 `adjacent = box_face.switchboxes - {box}` 非空再取邻盒；扩张循环内先收集 `(i, adj_box)`，若任一步邻接为空则放弃该生长方向并 `continue` 下一轮，避免部分替换与崩溃。
- **注释**：在 `coalesce` 内新增中文注释说明为何保守处理。

### 2. 配套仓库 `netlist-to-sch-via-skidl`（与本 fork 联用）

- **`convert_netlist.py`**：`--schematic-subdir` 默认值由 `kicad_generated` 改为 **`kicad_generated_h`**，与当前注入的 `human_readable=True` 流程一致。
- **`generated_script_patch.py`**：`_finalize_generated_skidl` 默认 `schematic_subdir` 改为 **`kicad_generated_h`**。
- **`.gitignore`**：增加 `kicad_generated_h/`；保留 `kicad_generated/` 以兼容旧产物。
- **示例 `*_skidl.py` / README**：原理图输出路径改为 **`kicad_generated_h`** 说明。

### 3. 验收

- 在 `ski2` 环境下对 `5micro_3.net` 重新 `convert_netlist` 后运行 `5micro_3_skidl.py`，**`human_readable=True`** 应能完成 schematic 生成（或进入既有 auto_stub 回退），且 `.kicad_sch` 位于 **`kicad_generated_h/`**。
