#include "pybindings_common.h"

#include "resources.h"

namespace py = pybind11;

namespace PyBindings {

void bindResources(py::module_& m) {
  py::module_ res = m.def_submodule("resources", "A story's own looks: textures from its files, variants of game meshes.");
  res.def("mesh_textures", [](const std::string& mesh) { return Resources::meshTextures(mesh); }, py::arg("mesh"),
          "The textures a game mesh (.3DS) is drawn with.");
  res.def("export_texture",
          [](const std::string& name, const std::string& path, std::tuple<float,float,float> tint, float strength,
             float brighten) {
            const float t[3] = {std::get<0>(tint), std::get<1>(tint), std::get<2>(tint)};
            return Resources::exportTexture(name, path, t, strength, brighten);
            }, py::arg("name"), py::arg("path"), py::arg("tint") = std::make_tuple(1.f,1.f,1.f),
          py::arg("strength") = 0.f, py::arg("brighten") = 1.f,
          "Write a game texture out as a PNG file, recoloured towards tint by strength (0 keeps it as it is).");
  res.def("export_mesh",
          [](const std::string& mesh, const std::string& path, std::tuple<float,float,float> tint, float strength,
             float brighten) {
            const float t[3] = {std::get<0>(tint), std::get<1>(tint), std::get<2>(tint)};
            return Resources::exportMeshObj(mesh, path, t, strength, brighten);
            }, py::arg("mesh"), py::arg("path"), py::arg("tint") = std::make_tuple(1.f,1.f,1.f),
          py::arg("strength") = 0.f, py::arg("brighten") = 1.f,
          "Write a game mesh (.3DS) out as OBJ with its MTL and PNG textures (recoloured if strength > 0), to be "
          "reshaped and read back as a story's own model.");
  res.def("register_texture", [](const std::string& name, const std::string& path) {
            Resources::registerTexture(name, path);
            }, py::arg("name"), py::arg("path"), "A texture name that loads from this image file.");
  res.def("register_mesh_variant",
          [](const std::string& alias, const std::string& base, const std::map<std::string,std::string>& textures) {
            if(!Resources::registerMeshVariant(alias, base, textures))
              return false;
            if(auto* w = Gothic::inst().world())
              w->refreshItemVisuals(alias);   // items loaded before it was registered are drawn now
            return true;
            }, py::arg("alias"), py::arg("base"), py::arg("textures"),
          "A mesh name that is the game mesh 'base' drawn with some textures swapped: {game texture: own name}.");
  res.def("register_mesh_file",
          [](const std::string& alias, const std::string& path, const std::string& texture, float scale) {
            if(!Resources::registerMeshFile(alias, path, texture, scale))
              return false;
            if(auto* w = Gothic::inst().world())
              w->refreshItemVisuals(alias);   // items loaded before it was registered are drawn now
            return true;
            }, py::arg("alias"), py::arg("path"), py::arg("texture") = "", py::arg("scale") = 1.f,
          "A mesh name (DM_....3DS) that is the Wavefront OBJ file 'path': y up, model facing -z, 1 unit = 'scale' cm, "
          "origin where it stands; drawn with the registered texture 'texture', or with its MTL file's images.");
  }

} // namespace PyBindings
