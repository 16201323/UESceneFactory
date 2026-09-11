# -*- coding: utf-8 -*-
"""
UE5 Python: 检查Plane网格UV布局 + 材质Panner连接
目标: 确定Panner speed_x平移的U方向对应网格哪个轴
"""
import unreal
import traceback

LOG_FILE = "C:/Users/25868/Desktop/UE5/MapForgeTest/check_plane_uv_result.txt"
MATERIAL_PATH = "/Game/Modular_Rural_Cabin/Materials/Masters/MM_Water"
PLANE_PATH = "/Engine/BasicShapes/Plane"

lines = []

def log(msg):
    lines.append(str(msg))

try:
    log("=" * 60)
    log("=== 1. Plane网格顶点+UV ===")
    log("=" * 60)

    plane = unreal.load_asset(PLANE_PATH)
    if not plane:
        log("ERROR: 无法加载Plane")
    else:
        log("Plane: " + plane.get_name())

        # 方法A: StaticMeshDescription
        try:
            smd = plane.get_editor_property("static_mesh_description")
            if smd:
                vc = smd.get_vertex_count()
                log("SMD顶点数: " + str(vc))
                uvcc = smd.get_uv_channel_count()
                log("UV通道数: " + str(uvcc))

                # 遍历顶点
                vit = smd.get_vertex_iterator()
                idx = 0
                for vid in vit:
                    pos = smd.get_vertex_position(vid)
                    log("  V" + str(idx) + " pos=(" + str(round(pos.x, 1)) + "," + str(round(pos.y, 1)) + "," + str(round(pos.z, 1)) + ")")
                    # 获取UV (通道0)
                    try:
                        uv = smd.get_uv(0, vid)
                        log("    UV0=(" + str(round(uv.x, 3)) + "," + str(round(uv.y, 3)) + ")")
                    except Exception as e2:
                        log("    UV获取失败: " + str(e2))
                    idx += 1
            else:
                log("SMD为None (引擎资源可能无描述数据)")
        except Exception as e:
            log("SMD方法异常: " + str(e))

        # 方法B: RenderData LOD
        try:
            rd = plane.get_editor_property("render_data")
            if rd:
                lod = rd.get_lod(0)
                vb = lod.get_vertex_buffer()
                ib = lod.get_index_buffer()
                nv = vb.get_num_vertices()
                ni = ib.get_num_indices()
                stride = vb.get_stride()
                nuv = vb.get_num_tex_coords()
                log("")
                log("RenderData LOD0:")
                log("  顶点数=" + str(nv) + " 索引数=" + str(ni))
                log("  stride=" + str(stride) + " UV通道=" + str(nuv))

                # 尝试读取顶点位置和UV
                raw = vb.get_raw_data(0, nv * stride)
                log("  原始数据大小=" + str(len(raw)) + " 字节")

                # stride通常=32或40: pos(12) + tangent(16) + uv(8 or 16)
                # 尝试不同stride解析
                import struct
                for s in [stride]:
                    if s >= 12:
                        log("")
                        log("  尝试 stride=" + str(s) + " 解析前4个顶点:")
                        for vi in range(min(nv, 4)):
                            base = vi * s
                            if base + 12 <= len(raw):
                                px, py, pz = struct.unpack_from("<fff", raw, base)
                                log("    V" + str(vi) + " pos=(" + str(round(px, 1)) + "," + str(round(py, 1)) + "," + str(round(pz, 1)) + ")")
                                # UV可能在偏移12 (紧跟位置) 或 28
                                for uv_offset in [12, 28, 24, 20, 16]:
                                    if base + uv_offset + 8 <= len(raw):
                                        try:
                                            uu, vv = struct.unpack_from("<ff", raw, base + uv_offset)
                                            if 0 <= uu <= 1 and 0 <= vv <= 1:
                                                log("      UV@(off=" + str(uv_offset) + ")=(" + str(round(uu, 3)) + "," + str(round(vv, 3)) + ")")
                                        except:
                                            pass
        except Exception as e:
            log("RenderData方法异常: " + str(e))

    log("")
    log("=" * 60)
    log("=== 2. MM_Water材质表达式 ===")
    log("=" * 60)

    mat = unreal.load_asset(MATERIAL_PATH)
    if not mat:
        log("ERROR: 无法加载材质")
    else:
        log("材质: " + mat.get_name())

        try:
            expressions = unreal.MaterialEditingLibrary.get_material_expressions(mat)
        except Exception:
            expressions = mat.get_editor_property("expressions")

        log("表达式总数: " + str(len(expressions)))

        panner_info = []
        texcoord_info = []

        for i, expr in enumerate(expressions):
            cn = expr.get_class().get_name()
            extra = ""

            if "Panner" in cn:
                try:
                    sx = expr.get_editor_property("speed_x")
                    sy = expr.get_editor_property("speed_y")
                    extra = " speed_x=" + str(sx) + " speed_y=" + str(sy)
                    panner_info.append((i, cn, sx, sy))
                except Exception:
                    pass

            if "TextureCoordinate" in cn or "TexCoord" in cn:
                try:
                    ci = expr.get_editor_property("coordinate_index")
                    ut = expr.get_editor_property("utiling")
                    vt = expr.get_editor_property("vtiling")
                    extra = " coord=" + str(ci) + " utiling=" + str(ut) + " vtiling=" + str(vt)
                    texcoord_info.append((i, cn, ci, ut, vt))
                except Exception:
                    pass

            if "ScalarParameter" in cn:
                try:
                    pn = expr.get_editor_property("parameter_name")
                    dv = expr.get_editor_property("default_value")
                    extra = " name=" + str(pn) + " default=" + str(dv)
                except Exception:
                    pass

            if "TextureSample" in cn or "TextureObject" in cn:
                try:
                    tex = expr.get_editor_property("texture")
                    if tex:
                        extra = " texture=" + tex.get_name()
                except Exception:
                    pass

            log("  [" + str(i) + "] " + cn + extra)

        # 汇总
        log("")
        log("=== Panner汇总 ===")
        for pi in panner_info:
            log("  Panner#" + str(pi[0]) + ": speed_x=" + str(pi[2]) + " speed_y=" + str(pi[3]))

        log("")
        log("=== TexCoord汇总 ===")
        for ti in texcoord_info:
            log("  TexCoord#" + str(ti[0]) + ": coord=" + str(ti[2]) + " utiling=" + str(ti[3]) + " vtiling=" + str(ti[4]))

        if not texcoord_info:
            log("  (无显式TexCoord节点, Panner使用默认TexCoord)")

except Exception as e:
    log("FATAL: " + str(e))
    log(traceback.format_exc())

log("")
log("完成。")

try:
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("CHECK_PLANE_UV_DONE")
    print("结果: " + LOG_FILE)
except Exception as e:
    print("写入失败: " + str(e))
    for line in lines:
        print(line)
