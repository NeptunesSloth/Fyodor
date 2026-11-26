"""Fyodor's library shuffle (a riffle, then a bridge), authored in Blender and exported as a glTF clip.

The 3D table only plays the exported file (frontend/src/table3d/assets/riffle.glb, loaded with three's GLTFLoader):
Blender is never needed to run Fyodor. To change the shuffle, edit this script and run it again in any Blender 4.2+:

    blender -b -P packaging/blender/riffle.py -- frontend/src/table3d/assets/riffle.glb

It works in a scene of its own ("FyodorRiffle"), so it never touches whatever else the open file holds.

Units are the table's (table3d/layout.ts): a card is 0.84 wide and 1.17 long; the pile's top centre is the origin.
Twelve cards: the lower six split to the left, the upper six to the right; their inner edges lift (shape keys
lift_r / lift_l, the card bending under the thumbs), they fall back in interleaved, bottom first, are pushed
together, bowed into a bridge (shape key arch) and let go flat and square.
"""

import math
import os
import sys

import bmesh
import bpy

FPS = 30
N = 12
W, L, T = 0.84, 1.17, 0.012  # card width, length, thickness (thinner than the table's exaggerated pile cards)
GAP = 0.013  # height per card in a pile
NX, NY = 8, 10  # grid segments across the width and along the length (enough to bend smoothly)
LIFT = 0.2  # how far a lifted inner edge rises (exaggerated: the table is seen from well above)
ARCH = 0.18  # how high the bridge bows


def out_path() -> str:
    if "--" in sys.argv:
        return os.path.abspath(sys.argv[sys.argv.index("--") + 1])
    return os.path.abspath(globals().get("OUT", "riffle.glb"))


def fresh_scene() -> bpy.types.Scene:
    old = bpy.data.scenes.get("FyodorRiffle")
    if old:
        for ob in list(old.objects):
            if ob.type != "MESH" or not ob.name.startswith("riffle"):
                continue  # (anything else someone added to the scene, a preview camera, is left to them)
            mesh = ob.data
            bpy.data.objects.remove(ob)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        bpy.data.scenes.remove(old)
    sc = bpy.data.scenes.new("FyodorRiffle")
    sc.render.fps = FPS
    sc.frame_start = 0
    sc.frame_end = 30
    return sc


def material(name: str, rgb: tuple[float, float, float], rough: float) -> bpy.types.Material:
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def card_mesh(name: str, back: bpy.types.Material, edge: bpy.types.Material) -> bpy.types.Mesh:
    """A thin card as a grid box: top and bottom faces carry the back (UV 0..1 over the card), the sides the edge."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    grid = {}
    for side, z in (("top", T / 2), ("bot", -T / 2)):
        for j in range(NY + 1):
            for i in range(NX + 1):
                grid[side, i, j] = bm.verts.new(((i / NX - 0.5) * W, (j / NY - 0.5) * L, z))

    def face(vs, mat_index, uvs=None):
        f = bm.faces.new(vs)
        f.material_index = mat_index
        if uvs:
            for loop, co in zip(f.loops, uvs, strict=True):
                loop[uv].uv = co
        return f

    for j in range(NY):
        for i in range(NX):
            co = [(i / NX, j / NY), ((i + 1) / NX, j / NY), ((i + 1) / NX, (j + 1) / NY), (i / NX, (j + 1) / NY)]
            face([grid["top", i, j], grid["top", i + 1, j], grid["top", i + 1, j + 1], grid["top", i, j + 1]], 0, co)
            face([grid["bot", i, j + 1], grid["bot", i + 1, j + 1], grid["bot", i + 1, j], grid["bot", i, j]], 0,
                 [co[3], co[2], co[1], co[0]])
    ring = ([(i, 0) for i in range(NX)] + [(NX, j) for j in range(NY)] + [(i, NY) for i in range(NX, 0, -1)]
            + [(0, j) for j in range(NY, 0, -1)])
    for k, (i, j) in enumerate(ring):
        i2, j2 = ring[(k + 1) % len(ring)]
        face([grid["top", i, j], grid["bot", i, j], grid["bot", i2, j2], grid["top", i2, j2]], 1)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(back)
    me.materials.append(edge)
    for p in me.polygons:
        p.use_smooth = True
    return me


def add_shape_keys(ob: bpy.types.Object) -> None:
    ob.shape_key_add(name="Basis")
    hw, hl = W / 2, L / 2
    for name, fn in (
        # the inner long edge lifts under the thumb: a curl across the width
        ("lift_r", lambda x, y: LIFT * max(0.0, x / hw) ** 2),
        ("lift_l", lambda x, y: LIFT * max(0.0, -x / hw) ** 2),
        # the bridge: bowed up along the length, the ends held down
        ("arch", lambda x, y: ARCH * (1 - (y / hl) ** 2)),
    ):
        key = ob.shape_key_add(name=name)
        for v, kv in zip(ob.data.vertices, key.data, strict=True):
            kv.co = (v.co.x, v.co.y, v.co.z + fn(v.co.x, v.co.y))


def keys(ob: bpy.types.Object, frame: float, x: float, z: float, lift: float = 0.0, arch: float = 0.0, yaw: float = 0.0) -> None:
    ob.location = (x, 0.0, z)
    ob.rotation_euler = (0.0, 0.0, yaw)
    ob.keyframe_insert("location", frame=frame)
    ob.keyframe_insert("rotation_euler", frame=frame)
    blocks = ob.data.shape_keys.key_blocks
    side = "lift_r" if x <= 0 else "lift_l"  # (the left half's inner edge is its right one)
    for name in ("lift_r", "lift_l", "arch"):
        blocks[name].value = lift if name == side else arch if name == "arch" else 0.0
        blocks[name].keyframe_insert("value", frame=frame)


def build(sc: bpy.types.Scene) -> None:
    back = material("FyodorCardBack", (0.16, 0.11, 0.08), 0.8)
    edge = material("FyodorCardEdge", (0.86, 0.83, 0.76), 0.9)
    half = N // 2
    for i in range(N):
        ob = bpy.data.objects.new(f"riffle{i:02d}", card_mesh(f"riffle{i:02d}", back, edge))
        sc.collection.objects.link(ob)
        add_shape_keys(ob)
        lower = i < half
        k = i if lower else i - half  # place within its half
        order = k * 2 + (0 if lower else 1)  # where it ends up in the interleaved pile
        s = -1 if lower else 1
        pile = i * GAP + T / 2
        lifted = k * GAP + T / 2 + 0.09
        final = order * GAP + T / 2
        keys(ob, 0, 0.0, pile)
        keys(ob, 7, s * 0.5, lifted, yaw=s * -0.05)  # the halves split apart
        keys(ob, 10, s * 0.44, lifted + 0.02, lift=1.0, yaw=s * -0.06)  # inner edges lifted, just meeting
        drop = 10 + order * 0.8  # released one by one, bottom first
        keys(ob, drop, s * 0.44, lifted + 0.02, lift=1.0, yaw=s * -0.06)
        keys(ob, drop + 2.2, s * 0.24, final, lift=0.0, yaw=s * -0.04)  # falls flat onto the card below
        keys(ob, 21, s * 0.24, final, yaw=s * -0.04)
        keys(ob, 23.5, s * 0.06, final + 0.004, arch=0.4)  # pushed together, bowing
        keys(ob, 25.5, 0.0, final + 0.012, arch=1.0)  # the bridge
        keys(ob, 30, 0.0, final)  # let go: flat and square


def export(sc: bpy.types.Scene, path: str) -> None:
    window = bpy.context.window
    previous = window.scene if window else None
    if window:
        window.scene = sc
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_active_scene=True, export_animations=True, export_morph=True,
            export_animation_mode="SCENE", export_force_sampling=True, export_frame_range=True, export_yup=True,
            export_apply=False, export_texcoords=True, export_normals=True, export_cameras=False, export_lights=False,
        )
    finally:
        if window and previous:
            window.scene = previous


sc = fresh_scene()
build(sc)
export(sc, out_path())
print("riffle written to", out_path())
