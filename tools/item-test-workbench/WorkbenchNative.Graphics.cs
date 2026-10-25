using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Content;
using ReLogic.Content.Readers;

// Real optional software-OpenGL context. No fabricated Texture2D/Asset fields or game assets.
internal sealed class WorkbenchGraphicsContext : IDisposable
{
    private static readonly Dictionary<string,IntPtr> NativeLibraries=new();
    private static bool resolverInstalled;
    private readonly Game game;
    private readonly GraphicsDeviceManager manager;
    private readonly AssetRepository assets;
    public GraphicsDevice Device => manager.GraphicsDevice;
    public Asset<Texture2D> ItemTexture { get; }
    public JsonObject Provenance { get; }
    public WorkbenchGraphicsContext(string itemPngPath,string? previewPath=null)
    {
        if(!File.Exists(itemPngPath)) throw new FileNotFoundException("Exact repository GeneratedItem.png required for client item geometry",itemPngPath);
        // Supported offscreen SDL/EGL backend; never starts X11, Xvfb, a browser, or network services.
        SetEnvironment("SDL_VIDEODRIVER","offscreen");
        SetEnvironment("SDL_AUDIODRIVER","dummy");
        SetEnvironment("FNA3D_FORCE_DRIVER","OpenGL");
        SetEnvironment("LIBGL_ALWAYS_SOFTWARE","1");
        string cache=Path.Combine(Path.GetTempPath(),"icl-workbench-mesa"); Directory.CreateDirectory(cache);
        SetEnvironment("MESA_SHADER_CACHE_DIR",cache);
        SetEnvironment("XDG_CACHE_HOME",cache);
        PrepareNativeLibraries();
        game=new Game();
        manager=new GraphicsDeviceManager(game) { PreferredBackBufferWidth=128,PreferredBackBufferHeight=128,SynchronizeWithVerticalRetrace=false };
        ((IGraphicsDeviceManager)manager).CreateDevice();
        AssetRepository.SetMainThread();
        var readers=new AssetReaderCollection();readers.RegisterReader(new PngReader(Device),".png");
        assets=new AssetRepository(readers);
        using(var input=File.OpenRead(itemPngPath)) ItemTexture=assets.CreateUntracked<Texture2D>(input,"GeneratedItem.png",AssetRequestMode.ImmediateLoad);
        if(ItemTexture.State!=AssetState.Loaded) throw new InvalidOperationException("Native PNG asset did not reach Loaded state");
        // Actual GPU API readback validates creation/upload, independently of asset dimensions.
        var readback=new Color[ItemTexture.Value.Width*ItemTexture.Value.Height];ItemTexture.Value.GetData(readback);
        Provenance=new JsonObject { ["backend"]="SDL offscreen / FNA3D OpenGL / software Mesa",["renderer"]=GlString(0x1F01),["version"]=GlString(0x1F02),["vendor"]=GlString(0x1F00),["graphicsProfile"]=Device.GraphicsProfile.ToString(),["assetPath"]=Path.GetFullPath(itemPngPath),["assetSha256"]=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(itemPngPath))).ToLowerInvariant(),["assetState"]=ItemTexture.State.ToString(),["textureWidth"]=ItemTexture.Value.Width,["textureHeight"]=ItemTexture.Value.Height,["textureCreation"]="Actual ReLogic PngReader and AssetRepository.CreateUntracked; real Texture2D upload/readback",["renderScope"]="Optional asset preview, not Terraria world rendering",["previewPath"]=previewPath is null?null:Path.GetFullPath(previewPath) };
        if(previewPath is not null) SavePreview(previewPath);
    }
    public void SavePreview(string path)
    {
        using var target=new RenderTarget2D(Device,128,128);
        Device.SetRenderTarget(target);Device.Clear(new Color(20,24,32));
        using(var batch=new SpriteBatch(Device)) { batch.Begin(SpriteSortMode.Deferred,BlendState.AlphaBlend,SamplerState.PointClamp,DepthStencilState.None,RasterizerState.CullNone);batch.Draw(ItemTexture.Value,new Rectangle(16,16,96,96),Color.White);batch.End(); }
        Device.SetRenderTarget(null);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        using var output=File.Create(path);target.SaveAsPng(output,128,128);
    }
    [DllImport("libc",EntryPoint="setenv",SetLastError=true)] private static extern int NativeSetEnvironment(string name,string value,int overwrite);
    private static void SetEnvironment(string name,string value) { Environment.SetEnvironmentVariable(name,value);if(OperatingSystem.IsLinux() && NativeSetEnvironment(name,value,1)!=0) throw new InvalidOperationException("Unable to configure native graphics environment: "+name); }
    private static void PrepareNativeLibraries()
    {
        if(resolverInstalled) return;
        if(!OperatingSystem.IsLinux()) throw new PlatformNotSupportedException("Verified software graphics backend currently requires Linux SDL offscreen");
        string? explicitDirectory=Environment.GetEnvironmentVariable("INFINI_TML_NATIVE_DIR");
        var roots=new List<string>();if(!string.IsNullOrEmpty(explicitDirectory)) roots.Add(explicitDirectory);
        roots.AddRange((Environment.GetEnvironmentVariable("LD_LIBRARY_PATH")??"").Split(':',StringSplitOptions.RemoveEmptyEntries));roots.Add(AppContext.BaseDirectory);
        foreach(var pair in new[]{("SDL2","libSDL2-2.0.so.0"),("FNA3D","libFNA3D.so.0"),("FAudio","libFAudio.so.0"),("theorafile","libtheorafile.so")}) {
            string? found=null;foreach(string root in roots) { string candidate=Path.Combine(root,pair.Item2);if(File.Exists(candidate)){found=candidate;break;} }
            if(found is null) throw new FileNotFoundException("Set INFINI_TML_NATIVE_DIR to official tModLoader Libraries/Native/Linux; missing "+pair.Item2);
            NativeLibraries[pair.Item1]=NativeLibrary.Load(Path.GetFullPath(found));
        }
        NativeLibrary.SetDllImportResolver(typeof(Game).Assembly,(name,assembly,path)=>NativeLibraries.TryGetValue(name,out var handle)?handle:IntPtr.Zero);
        resolverInstalled=true;
    }
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr GetProc([MarshalAs(UnmanagedType.LPUTF8Str)] string name);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr GetString(uint name);
    private static string GlString(uint name)
    {
        var getProc=Marshal.GetDelegateForFunctionPointer<GetProc>(NativeLibrary.GetExport(NativeLibraries["SDL2"],"SDL_GL_GetProcAddress"));
        IntPtr address=getProc("glGetString");if(address==IntPtr.Zero) return "unavailable";
        return Marshal.PtrToStringAnsi(Marshal.GetDelegateForFunctionPointer<GetString>(address)(name))??"unavailable";
    }
    public void Dispose(){ItemTexture.Dispose();assets.Dispose();((IDisposable)manager).Dispose();game.Dispose();}
}
