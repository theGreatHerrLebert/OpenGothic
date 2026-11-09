// Dumps the placed items, containers and locks of the game's worlds as JSON lines.
//
//   c++ -std=c++20 -Ilib/ZenKit/include -Ibuild/lib/ZenKit/include python/dm/tools/world_dump.cpp build/lib/ZenKit/libzenkit.a \
//       build/lib/ZenKit/vendor/libsquish/libsquish.a -o build/world_dump
//   world_dump <game>/Data/Worlds.vdf <game>/Data/Worlds_Addon.vdf <out.jsonl>
#include <fstream>
#include <iostream>
#include <zenkit/Vfs.hh>
#include <zenkit/Stream.hh>
#include <zenkit/World.hh>
#include <zenkit/vobs/MovableObject.hh>
#include <zenkit/vobs/Misc.hh>

using namespace zenkit;

static std::string esc(const std::string& s) {
  std::string r;
  for(unsigned char c:s) {
    if(c=='"' || c=='\\') { r+='\\'; r+=char(c); }
    else if(c<32) r+=' ';
    else if(c<128) r+=char(c);
    else { r+=char(0xC0|(c>>6)); r+=char(0x80|(c&0x3F)); }
    }
  return r;
  }

static void walk(std::ostream& out, const std::string& world, const std::shared_ptr<VirtualObject>& v) {
  if(!v) return;
  std::string extra;
  const char* kind = nullptr;
  if(auto i=std::dynamic_pointer_cast<VItem>(v)) { kind="item"; extra=",\"instance\":\""+esc(i->instance)+"\""; }
  else if(auto c=std::dynamic_pointer_cast<VContainer>(v)) {
    kind="container";
    extra=",\"locked\":"+std::string(c->locked?"true":"false")+",\"key\":\""+esc(c->key)+"\",\"pick\":\""+esc(c->pick_string)+"\",\"contents\":\""+esc(c->contents)+"\"";
    }
  else if(auto d=std::dynamic_pointer_cast<VDoor>(v)) {
    kind="door";
    extra=",\"locked\":"+std::string(d->locked?"true":"false")+",\"key\":\""+esc(d->key)+"\",\"pick\":\""+esc(d->pick_string)+"\"";
    }
  if(kind)
    out<<"{\"world\":\""<<world<<"\",\"kind\":\""<<kind<<"\",\"name\":\""<<esc(v->vob_name)<<"\",\"x\":"<<v->position.x<<",\"y\":"<<v->position.y<<",\"z\":"<<v->position.z<<extra<<"}\n";
  for(auto& c:v->children) walk(out,world,c);
  }

int main(int, char** argv) {
  Vfs vfs;
  vfs.mount_disk(argv[1], VfsOverwriteBehavior::OLDER);
  vfs.mount_disk(argv[2], VfsOverwriteBehavior::OLDER);
  std::ofstream out(argv[3]);
  for(std::string name:{"NEWWORLD.ZEN","OLDWORLD.ZEN","DRAGONISLAND.ZEN","ADDONWORLD.ZEN"}) {
    auto* node=vfs.find(name);
    if(!node) { std::cerr<<"missing "<<name<<"\n"; continue; }
    auto r=node->open_read();
    World w; w.load(r.get(), GameVersion::GOTHIC_2);
    for(auto& v:w.world_vobs) walk(out,name,v);
    for(auto& p:w.way_net->points) out<<"{\"world\":\""<<name<<"\",\"kind\":\"waypoint\",\"name\":\""<<esc(p->name)<<"\",\"x\":"<<p->position.x<<",\"y\":"<<p->position.y<<",\"z\":"<<p->position.z<<"}\n";
    }
  }
