using System;
using System.IO;
using System.Reflection;
using System.Text;
using Terraria.ModLoader.Core;

// Test-only packer: exercise the actual tML archive writer, not a mock format.
if (args.Length != 3) throw new ArgumentException("Expected fixture DLL, source root, output .tmod");
const BindingFlags all = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
Type propsType = typeof(TmodFile).Assembly.GetType("Terraria.ModLoader.Core.BuildProperties", true)!;
object props = propsType.GetMethod("ReadBuildFile", all)!.Invoke(null, new object[] { Path.GetFullPath(args[1]) })!;
byte[] info = (byte[])propsType.GetMethod("ToBytes", all)!.Invoke(props, null)!;
Version version = (Version)propsType.GetField("version", all)!.GetValue(props)!;
string name = AssemblyName.GetAssemblyName(args[0]).Name!;
var file = (TmodFile)Activator.CreateInstance(typeof(TmodFile), all, null,
    new object[] { Path.GetFullPath(args[2]), name, version }, null)!;
MethodInfo add = typeof(TmodFile).GetMethod("AddFile", all)!;
add.Invoke(file, new object[] { "Info", info });
add.Invoke(file, new object[] { name + ".dll", File.ReadAllBytes(args[0]) });
add.Invoke(file, new object[] { "workbench-original.txt", Encoding.UTF8.GetBytes("fixture archive bytes") });
typeof(TmodFile).GetMethod("Save", all)!.Invoke(file, null);
