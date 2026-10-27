#!/usr/bin/env python3
"""Compile and run IFC adapter path/transport guards without launching the game."""
import argparse
import html
import os
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tml-reference-dir', type=Path, required=True, help='Matching tModLoader reference DLL directory')
    parser.add_argument('--ifc-dll', type=Path, required=True, help='Built InfiniCrafterLocal DLL from the matching version')
    parser.add_argument('--dotnet', default=os.environ.get('DOTNET', 'dotnet'))
    parser.add_argument('--dotnet-runtime', help='Optional .NET 8 runtime executable when the SDK uses a different installation')
    args = parser.parse_args()
    refs = args.tml_reference_dir.expanduser().resolve(strict=True)
    ifc = args.ifc_dll.expanduser().resolve(strict=True)
    if not refs.is_dir() or not (refs / 'tModLoader.dll').is_file() or not ifc.is_file():
        parser.error('Provide a tModLoader DLL directory and a built IFC DLL')
    source = HERE / 'IFCWorkbenchIFCAdapter' / 'IFCWorkbenchIFCAdapter.cs'
    checks = HERE / 'IFCAdapterGuardChecks.cs'
    escape = lambda p: html.escape(str(p), quote=True)
    with tempfile.TemporaryDirectory(prefix='ifc-adapter-guards-build-') as temporary:
        root = Path(temporary)
        (root / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>', encoding='utf-8')
        (root / 'checks.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><TargetFramework>net8.0</TargetFramework><OutputType>Exe</OutputType>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems><Nullable>enable</Nullable><LangVersion>latest</LangVersion>
  </PropertyGroup>
  <ItemGroup><Compile Include="{escape(source)}"/><Compile Include="{escape(checks)}"/>
    <Reference Include="{escape(refs / '*.dll')}"/><Reference Include="{escape(ifc)}"/>
  </ItemGroup>
</Project>''', encoding='utf-8')
        subprocess.run([args.dotnet, 'build', 'checks.csproj', '-c', 'Release', '--configfile', 'NuGet.Config', '-v:q'], cwd=root, check=True)
        return subprocess.run([args.dotnet_runtime or args.dotnet, str(root / 'bin/Release/net8.0/checks.dll')], cwd=root).returncode


if __name__ == '__main__':
    raise SystemExit(main())
