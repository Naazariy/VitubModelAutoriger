import struct
from test_build import build_moc3, table, decode_id_64

class Moc3ReaderNew:
    MAGIC = b"MOC3"

    @classmethod
    def read_from_file(cls, path: str):
        with open(path, "rb") as f:
            data = f.read()
        return cls.parse_bytes(data)

    @classmethod
    def parse_bytes(cls, data: bytes):
        if len(data) < 64:
            raise ValueError(f"File size too small for .moc3: {len(data)} bytes < 64 bytes")

        magic = data[:4]
        if magic != cls.MAGIC:
            raise ValueError(f"Invalid MOC3 magic header: expected {cls.MAGIC}, got {magic}")

        version, is_big_endian = struct.unpack_from("<BB", data, 4)
        if is_big_endian != 0:
            raise ValueError(f"Unsupported endianness: {is_big_endian} (expected 0 Little-Endian)")

        result = {
            "magic": magic.decode("ascii", errors="replace"),
            "version": version,
            "is_big_endian": is_big_endian,
            "total_size": len(data),
            "is_64_aligned": (len(data) % 64 == 0)
        }

        if len(data) >= 704:
            section_offsets = list(struct.unpack_from("<160I", data, 64))
            result["section_offsets"] = section_offsets

            cnt_off = section_offsets[0] or 0x07C0
            if len(data) >= cnt_off + 92: # at least 23 uint32s
                counts = struct.unpack_from("<23I", data, cnt_off)
                result["counts"] = {
                    "parts": counts[0],
                    "deformers": counts[1],
                    "warp_deformers": counts[2],
                    "rotation_deformers": counts[3],
                    "art_meshes": counts[4],
                    "parameters": counts[5],
                    "part_keyforms": counts[6],
                    "warp_deformer_keyforms": counts[7],
                    "rotation_deformer_keyforms": counts[8],
                    "art_mesh_keyforms": counts[9],
                    "keyform_positions": counts[10],
                    "param_binding_indices": counts[11],
                    "keyform_bindings": counts[12],
                    "param_bindings": counts[13],
                    "keys": counts[14],
                    "uvs": counts[15],
                    "position_indices": counts[16],
                    "drawable_masks": counts[17],
                    "draw_order_groups": counts[18],
                    "draw_order_group_objects": counts[19],
                    "glue": counts[20],
                    "glue_info": counts[21],
                    "glue_keyforms": counts[22],
                }

            canvas_off = section_offsets[1] or 0x0840
            if len(data) >= canvas_off + 21:
                canvas_fields = struct.unpack_from("<5fB", data, canvas_off)
                result["canvas_info"] = {
                    "pixels_per_unit": canvas_fields[0],
                    "origin_x": canvas_fields[1],
                    "origin_y": canvas_fields[2],
                    "canvas_width": canvas_fields[3],
                    "canvas_height": canvas_fields[4],
                    "flags": canvas_fields[5],
                }

            # Parts (Sec 3)
            p_ids_off = section_offsets[3]
            n_parts = result.get("counts", {}).get("parts", 0)
            if p_ids_off and len(data) >= p_ids_off + n_parts * 64:
                part_ids = []
                for i in range(n_parts):
                    str_bytes = data[p_ids_off + i * 64 : p_ids_off + (i + 1) * 64]
                    part_ids.append(decode_id_64(str_bytes))
                result["part_ids"] = part_ids

            # Drawables / ArtMeshes (Sec 33)
            d_ids_off = section_offsets[33]
            n_meshes = result.get("counts", {}).get("art_meshes", 0)
            if d_ids_off and len(data) >= d_ids_off + n_meshes * 64:
                mesh_ids = []
                for i in range(n_meshes):
                    str_bytes = data[d_ids_off + i * 64 : d_ids_off + (i + 1) * 64]
                    mesh_ids.append(decode_id_64(str_bytes))
                result["art_mesh_ids"] = mesh_ids

            # Parameters (Sec 50)
            p_ids_off = section_offsets[50]
            n_params = result.get("counts", {}).get("parameters", 0)
            if p_ids_off and len(data) >= p_ids_off + n_params * 64:
                param_ids = []
                for i in range(n_params):
                    str_bytes = data[p_ids_off + i * 64 : p_ids_off + (i + 1) * 64]
                    param_ids.append(decode_id_64(str_bytes))
                result["parameter_ids"] = param_ids

            # Keys (Sec 77)
            k_off = section_offsets[77]
            n_keys = result.get("counts", {}).get("keys", 0)
            if k_off and len(data) >= k_off + n_keys * 4:
                result["keys"] = list(struct.unpack_from(f"<{n_keys}f", data, k_off))

        return result

# Test on Hiyori
h_parsed = Moc3ReaderNew.read_from_file("output/hiyori_vts/hiyori.moc3")
print("Hiyori parsed successfully!")
print("Hiyori version:", h_parsed["version"])
print("Hiyori counts art_meshes:", h_parsed["counts"]["art_meshes"])
print("Hiyori first 3 art meshes:", h_parsed["art_mesh_ids"][:3])
print("Hiyori first 3 params:", h_parsed["parameter_ids"][:3])

# Test on generated model
b = build_moc3(table)
gen_parsed = Moc3ReaderNew.parse_bytes(b)
print("\nGenerated model parsed successfully!")
print("Gen version:", gen_parsed["version"])
print("Gen counts art_meshes:", gen_parsed["counts"]["art_meshes"])
print("Gen art mesh IDs:", gen_parsed["art_mesh_ids"])
print("Gen param IDs:", gen_parsed["parameter_ids"])
print("Gen keys:", gen_parsed["keys"])
