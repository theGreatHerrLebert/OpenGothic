#pragma once

#include <zenkit/MultiResolutionMesh.hh>

#include <string>
#include <vector>

// A Wavefront OBJ file read into the game's own mesh form, so it is packed, drawn, culled and shown in the inventory
// exactly as a mesh from the game's archives.
//
// The file is expected as Blender writes it by default ("Y up, -Z forward", right-handed, faces counter-clockwise
// seen from the front): y is up, 1 unit is `scale` centimetres (Gothic's unit; scale 100 for a model made in metres),
// and its origin is where the item stands. It is taken into Gothic's left-handed space by negating z (so it looks as
// it did in Blender, not mirrored), and v is flipped (OBJ's v runs up, the game's down). Polygons are cut into
// triangle fans; corners without a normal get the smooth normal of their position. One sub-mesh per `usemtl`
// material, in order of first use.
namespace ObjMesh {
  struct SubInfo {
    std::string texFile;   // map_Kd of its material in the MTL file, resolved to a path; empty: none
    };

  bool load(const std::string& path, float scale, zenkit::MultiResolutionMesh& out, std::vector<SubInfo>& info,
            std::string& error);
  }
