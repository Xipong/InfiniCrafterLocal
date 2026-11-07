# Bundled managed dependency

`ICSharpCode.Decompiler.dll` is the unmodified managed ILSpy engine **8.2.0.7535**,
from the official [NuGet package](https://www.nuget.org/packages/ICSharpCode.Decompiler/8.2.0.7535).
Its source revision is `95108c967af69642f0f445212f350ec451354b98`.

| Artifact | SHA256 |
|---|---|
| Original NuGet package | `e015acd3855af6973f48b78c03fbcaa01c9d870f81bbab3d303b68a3f51c7edf` |
| `lib/netstandard2.0/ICSharpCode.Decompiler.dll` | `d174072a16aa758a39d160f70ce924103898fae2b8506b48f70d6909e25a1fd0` |

The engine only reads assembly metadata and IL for parent source observations.
It is shipped inside the mod through `dllReferences` and requires no installed
ILSpy application, external process or runtime download. Its immutable collections
and metadata APIs are provided by the existing .NET 8 runtime.

[MIT notices](ICSharpCode.Decompiler.LICENSE.txt) cover ILSpy and its included
Humanizer code. The package verifier checks the exact bundled DLL and notices.
