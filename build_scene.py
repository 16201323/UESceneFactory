# ============================================================================
# build_scene.py - JSON/YAML 场景描述 → UE5 umap 关卡转换工具 (可复用 CLI)
# ============================================================================
# 用法:
#   1. 编辑器内控制台:  py c:/.../build_scene.py c:/.../scene.yaml
#   2. 无头模式:
#      UnrealEditor-Cmd.exe project.uproject -unattended -nop4 -nosplash \
#        -nullrhi -stdout -ExecCmds="py build_scene.py scene.yaml | quit"
#   3. 不传参数时默认使用 farming_village.yaml
#
# 场景文件 schema (YAML/JSON 通用):
#   scene:        { name, target_level, description }
#   landscape:    { material, section_size_quads, num_subsections, component_count_x,
#                  component_count_y, location, scale }
#                  (UE5 正式 Landscape 地形, 需 LandscapeHelper C++ 插件)
#   ground:       { asset, location, rotation, scale, material_override }
#                  (静态网格地面, 与 landscape 二选一或叠加使用)
#   placements:   [ { asset, location, rotation, scale } | { asset, grid:{...} } ]
#   lighting:     { directional_light, sky_light, sky_atmosphere, height_fog }
#   weather:      { volumetric_clouds, post_process }
# ============================================================================

import unreal
import sys
import json
import os
import random