#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using ReLogic.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.GameInput;
using Terraria.ModLoader;
using Terraria.UI;

namespace InfiniCrafterLocal.Common.UI;

public sealed partial class RecipeJournalUISystem
{
    private static bool _lineageOpen, _lineageDragging, _lineageBrowserPending;
    private static RecipeLineageGraph? _lineage;
    private static GeneratedItemData[]? _lineageSnapshot;
    private static string _lineageRoot = "";
    private static float[] _lineageCaptionWidths = Array.Empty<float>();
    private static string[] _lineageCaptions = Array.Empty<string>();
    private static Item?[] _nativeNodes = Array.Empty<Item?>();
    private static Item? _publishedHover;
    private static int _highlightHover = -2;
    private static bool[] _highlightEdges = Array.Empty<bool>(), _highlightAncestors = Array.Empty<bool>(), _highlightDescendants = Array.Empty<bool>();
    private static string[] _edgeMultiplicityLabels = Array.Empty<string>();
    private static Vector2 _lineagePan, _dragCursor;
    private static float _lineageZoom = 1f;
    private static Rectangle _lineageCanvas;
    private static RasterizerState? LineageClip;
    private static readonly Color MapInk = new(79, 57, 34);

    private static void ResetLineage()
    {
        ClearLineageHover(); _lineageOpen = _lineageDragging = _lineageBrowserPending = false; _lineage = null;
        _lineageSnapshot = null; _lineageRoot = ""; _nativeNodes = Array.Empty<Item?>(); _lineageCaptions = Array.Empty<string>(); _lineageCaptionWidths = Array.Empty<float>();
        _highlightEdges = _highlightAncestors = _highlightDescendants = Array.Empty<bool>();
        _edgeMultiplicityLabels = Array.Empty<string>(); _highlightHover = -2;
        _lineagePan = Vector2.Zero; _lineageZoom = 1f; _lineageCanvas = Rectangle.Empty;
    }
    private static void ClearLineageHover()
    {
        // Only release the hover object we published, never another mod's item.
        if (_publishedHover is not null && ReferenceEquals(Main.HoverItem, _publishedHover)) Main.HoverItem = new Item();
        _publishedHover = null;
    }
    private static void GoBack()
    {
        ClearLineageHover(); _lineageDragging = _lineageBrowserPending = false;
        if (!History.TryPop(out var location)) { _lineageOpen = false; return; }
        _selected = location.Id; _lineageOpen = location.Lineage; _detailScroll = 0;
        SetSearchFocus(false); ClearLineageHover(); _lineageDragging = _lineageBrowserPending = false;
    }
    private static void OpenLineage(GeneratedItemData data)
    {
        History.Push(new(_selected, false)); _selected = data.Id; _lineageOpen = true;
        SetSearchFocus(false); _lineageRoot = "";
    }
    internal static float ClampLineageZoom(float zoom) => Math.Clamp(zoom, 0.25f, 2f);
    internal static Vector2 AnchoredLineagePan(Vector2 pan, Vector2 anchor, float previous, float next)
        => anchor - (anchor - pan) * (next / previous);
    internal static Vector2 ClampLineagePan(Vector2 pan, Vector2 viewport, Vector2 graph, float zoom)
    {
        // Keep at least a node-width of the map reachable rather than losing it offscreen.
        return new Vector2(Math.Clamp(pan.X, 40 - graph.X * zoom, Math.Max(40, viewport.X - 40)),
            Math.Clamp(pan.Y, 40 - graph.Y * zoom, Math.Max(40, viewport.Y - 40)));
    }
    internal static int HitLineageNode(RecipeLineageGraph graph, Vector2 cursor, Vector2 pan, float zoom)
    {
        for (int i = graph.Nodes.Length - 1; i >= 0; i--)
            if (Vector2.DistanceSquared(cursor, pan + graph.Nodes[i].Position * zoom) <= 28 * 28 * zoom * zoom) return i;
        return -1;
    }
    internal static void UpdateLineageInput()
    {
        // RB owns its registered binding and reads HoverItem itself. Yield only on the following
        // input update: autopause UpdateUI consumes the previous input before PostUpdateInput.
        if (_lineageBrowserPending) { _lineageBrowserPending = false; Close(); return; }
        RefreshLineageHover();
    }
    internal static void QueueLineageBrowserHandoff(bool browserInstalled)
    {
        if (_publishedHover is not null && browserInstalled
            && PlayerInput.Triggers.JustPressed.KeyStatus.TryGetValue("RecipeBrowser/QueryHoveredItem", out bool pressed) && pressed)
            _lineageBrowserPending = true;
    }
    private static void RefreshLineageHover()
    {
        if (!IsOpen || !_lineageOpen || _lineage is null || IsCovered() || _lineageDragging)
        { ClearLineageHover(); return; }
        // Input hooks use physical screen coordinates; the interface layer uses UI coordinates.
        Vector2 cursor = new Vector2(PlayerInput.MouseX, PlayerInput.MouseY) / Main.UIScale;
        if (!_lineageCanvas.Contains(cursor.ToPoint())) { ClearLineageHover(); return; }
        int index = HitLineageNode(_lineage, cursor - _lineageCanvas.TopLeft(), _lineagePan, _lineageZoom);
        if (index < 0 || _nativeNodes[index] is not { } native) { ClearLineageHover(); return; }
        ClearLineageHover(); Main.HoverItem = native; _publishedHover = native;
    }
    private static void ZoomLineage(float next, Vector2 anchor)
    {
        next = ClampLineageZoom(next);
        _lineagePan = AnchoredLineagePan(_lineagePan, anchor, _lineageZoom, next); _lineageZoom = next;
    }
    internal static (float Zoom, Vector2 Pan) FitLineageView(Vector2 viewport, Vector2 graph, Vector2 root)
    {
        float fit = Math.Min((viewport.X - 40f) / Math.Max(1, graph.X), (viewport.Y - 40f) / Math.Max(1, graph.Y));
        float zoom = ClampLineageZoom(fit);
        // At the readability floor, centering a huge graph would hide its selected root.
        // Frame that root near the top instead; dragging still reaches every ancestor.
        Vector2 pan = fit < .25f
            ? new Vector2(viewport.X / 2, Math.Min(50, viewport.Y / 2)) - root * zoom
            : (viewport - graph * zoom) / 2;
        return (zoom, pan);
    }
    private static void FitLineage(Rectangle canvas)
    {
        if (_lineage is null) return;
        var view = FitLineageView(canvas.Size(), new Vector2(_lineage.Width, _lineage.Height), _lineage.Nodes[_lineage.RootIndex].Position);
        _lineageZoom = view.Zoom; _lineagePan = view.Pan;
    }
    private static void EnsureLineage(Rectangle canvas)
    {
        if (_lineageRoot == _selected && (ReferenceEquals(_lineageSnapshot, _known)
            || (_lineageSnapshot is not null && _lineageSnapshot.SequenceEqual(_known))))
        { _lineageSnapshot = _known; return; }
        var selected = _known.FirstOrDefault(d => d.Id == _selected && d.RecipeMeta.WorldId == Main.worldID.ToString());
        bool rootChanged = _lineageRoot != _selected;
        _lineageRoot = _selected; _lineageSnapshot = _known;
        _lineage = selected is null ? null : RecipeLineageGraph.Build(selected, _known);
        _nativeNodes = new Item?[_lineage?.Nodes.Length ?? 0];
        _lineageCaptions = new string[_nativeNodes.Length];
        _lineageCaptionWidths = new float[_nativeNodes.Length];
        _highlightHover = -2; _highlightEdges = new bool[_lineage?.Edges.Length ?? 0];
        _highlightAncestors = new bool[_nativeNodes.Length]; _highlightDescendants = new bool[_nativeNodes.Length];
        _edgeMultiplicityLabels = _lineage?.Edges.Select(e => e.Multiplicity > 1 ? "×" + e.Multiplicity : "").ToArray() ?? Array.Empty<string>();
        if (_lineage is not null)
            for (int i = 0; i < _lineage.Nodes.Length; i++)
            {
                _lineageCaptions[i] = ClipLineageLabel(_lineage.Nodes[i].Label, 240);
                _lineageCaptionWidths[i] = FontAssets.MouseText.Value.MeasureString(_lineageCaptions[i]).X;
                if (_lineage.Nodes[i].Kind == RecipeLineageGraph.NodeKind.Native)
                    _nativeNodes[i] = RecipeNativeItemResolver.Resolve(_lineage.Nodes[i].Identity);
            }
        if (rootChanged) FitLineage(canvas);
    }
    private static bool DrawLineage(SpriteBatch sb)
    {
        ClearLineageHover();
        int margin = Math.Min(24, Math.Min(Main.screenWidth, Main.screenHeight) / 20);
        var book = new Rectangle(margin, margin, Main.screenWidth - margin * 2, Main.screenHeight - margin * 2);
        var canvas = new Rectangle(book.X + 32, book.Y + 62, Math.Max(0, book.Width - 64), Math.Max(0, book.Height - 104));
        var cursor = new Vector2(Main.mouseX, Main.mouseY);
        bool click = Main.mouseLeft && Main.mouseLeftRelease && !PlayerInput.IgnoreMouseInterface;
        bool inside = book.Contains(cursor.ToPoint());
        if (inside) { Main.LocalPlayer.mouseInterface = true; PlayerInput.LockVanillaMouseScroll("InfiniCrafterLocal: Lineage"); }
        Fill(sb, new Rectangle(0, 0, Main.screenWidth, Main.screenHeight), new Color(0, 0, 0, 75));
        DrawBook(sb, book);
        if (LineageButton(sb, new Rectangle(book.X + 18, book.Y + 16, 66, 28), Text("Back"), click, cursor)) { GoBack(); Main.mouseLeftRelease = false; return true; }
        LineageLabel(sb, Text("Lineage"), new Vector2(book.X + 96, book.Y + 17), new Color(216, 185, 115), .9f, Math.Max(0, book.Width - 340));
        if (LineageButton(sb, new Rectangle(book.Right - 48, book.Y + 16, 30, 28), "×", click, cursor)) { Close(); Main.mouseLeftRelease = false; return true; }
        if (canvas.Width < 60 || canvas.Height < 60) return true;
        EnsureLineage(canvas);
        if (_lineageCanvas != canvas) { _lineageCanvas = canvas; FitLineage(canvas); }
        Vector2 anchor = canvas.Size() * .5f;
        if (book.Width >= 340)
        {
        if (LineageButton(sb, new Rectangle(book.Right - 222, book.Y + 16, 30, 28), "−", click, cursor)) ZoomLineage(_lineageZoom / 1.2f, anchor);
        LineageCenterLabel(sb, $"{_lineageZoom:P0}", new Rectangle(book.Right - 190, book.Y + 20, 64, 24), new Color(216,185,115), .6f);
        if (LineageButton(sb, new Rectangle(book.Right - 124, book.Y + 16, 30, 28), "+", click, cursor)) ZoomLineage(_lineageZoom * 1.2f, anchor);
        if (LineageButton(sb, new Rectangle(book.Right - 88, book.Y + 16, 30, 28), "⊙", click, cursor)) FitLineage(canvas);
        }
        if (_lineage is null) { Paragraph(sb, Text("LineageMissing"), canvas, MapInk, .7f); return true; }
        bool onCanvas = canvas.Contains(cursor.ToPoint());
        if (onCanvas && PlayerInput.ScrollWheelDeltaForUI != 0)
            ZoomLineage(_lineageZoom * MathF.Pow(1.15f, Math.Clamp(PlayerInput.ScrollWheelDeltaForUI / 120f, -4, 4)), cursor - canvas.TopLeft());
        int hoverIndex = onCanvas ? HitLineageNode(_lineage, cursor - canvas.TopLeft(), _lineagePan, _lineageZoom) : -1;
        if (click && onCanvas && hoverIndex < 0) { _lineageDragging = true; _dragCursor = cursor; }
        if (!Main.mouseLeft) _lineageDragging = false;
        if (_lineageDragging) { _lineagePan += cursor - _dragCursor; _dragCursor = cursor; }
        _lineagePan = ClampLineagePan(_lineagePan, canvas.Size(), new Vector2(_lineage.Width, _lineage.Height), _lineageZoom);
        UpdateLineageHighlight(hoverIndex);
        DrawLineageGraph(sb, canvas, hoverIndex);
        DrawBookFold(sb, book);
        if (hoverIndex >= 0 && !_lineageDragging)
        {
            var node = _lineage.Nodes[hoverIndex];
            _hoverText = node.Label;
            if (node.Data is not null)
            {
                _hoverText += "\n" + Text("OpenParent");
                if (click) { Select(node.Data.Id); Main.mouseLeftRelease = false; return true; }
            }
            else if (_nativeNodes[hoverIndex] is { } native)
            {
                Main.HoverItem = native; _publishedHover = native;
                _hoverText += "\n" + Text(ModLoader.HasMod("RecipeBrowser") ? "LineageBrowserHint" : "LineageBrowserAbsent");
            }
            else _hoverText += "\n" + Text(node.Kind == RecipeLineageGraph.NodeKind.Cycle ? "LineageCycle" : node.Kind == RecipeLineageGraph.NodeKind.Truncated ? "LineageTruncated" : "LineageMissing");
        }
        QueueLineageBrowserHandoff(ModLoader.HasMod("RecipeBrowser"));
        if (_lineage.IsTruncated) LineageLabel(sb, Text("LineageTruncated"), new Vector2(canvas.X + 10, canvas.Bottom - 22), MapInk, .55f, canvas.Width - 20);
        if (click && inside) Main.mouseLeftRelease = false;
        if (_hoverText.Length > 0) Main.instance.MouseText(_hoverText);
        return true;
    }
    private static void UpdateLineageHighlight(int hover)
    {
        if (_lineage is null || hover == _highlightHover) return;
        _highlightHover = hover; Array.Clear(_highlightEdges);
        if (hover < 0) return;
        var ancestors = _highlightAncestors; var descendants = _highlightDescendants;
        Array.Clear(ancestors); Array.Clear(descendants);
        ancestors[hover] = descendants[hover] = true;
        bool changed;
        do
        {
            changed = false;
            foreach (var edge in _lineage.Edges)
            {
                if (ancestors[edge.Child] && !ancestors[edge.Parent]) { ancestors[edge.Parent] = true; changed = true; }
                if (descendants[edge.Parent] && !descendants[edge.Child]) { descendants[edge.Child] = true; changed = true; }
            }
        } while (changed);
        for (int i = 0; i < _lineage.Edges.Length; i++)
        {
            var edge = _lineage.Edges[i];
            _highlightEdges[i] = (ancestors[edge.Child] && ancestors[edge.Parent]) || (descendants[edge.Child] && descendants[edge.Parent]);
        }
    }
    internal static (int Start, int End) VisibleLineageSegments(Vector2[] path, float minY, float maxY)
    {
        // Layout routes are monotone in Y. Find intersecting segments without walking hidden generations.
        int Boundary(float y, bool inclusive)
        {
            int lo = 0, hi = path.Length;
            while (lo < hi)
            {
                int mid = lo + (hi - lo) / 2;
                if (inclusive ? path[mid].Y <= y : path[mid].Y < y) hi = mid; else lo = mid + 1;
            }
            return lo;
        }
        return (Math.Max(1, Boundary(maxY, true)), Math.Min(path.Length, Boundary(minY, false) + 1));
    }
    private static void DrawLineageGraph(SpriteBatch sb, Rectangle canvas, int hoverIndex)
    {
        if (_lineage is null) return;
        var device = sb.GraphicsDevice;
        Rectangle oldScissor = device.ScissorRectangle;
        var oldRasterizer = device.RasterizerState;
        sb.End();
        var transformed = Vector2.Transform(canvas.TopLeft(), Main.UIScaleMatrix);
        var transformedBottom = Vector2.Transform(canvas.BottomRight(), Main.UIScaleMatrix);
        device.ScissorRectangle = Rectangle.Intersect(device.Viewport.Bounds, new Rectangle((int)transformed.X, (int)transformed.Y,
            Math.Max(0,(int)(transformedBottom.X-transformed.X)), Math.Max(0,(int)(transformedBottom.Y-transformed.Y))));
        sb.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, SamplerState.LinearClamp, DepthStencilState.None, LineageClip, null, Main.UIScaleMatrix);
        try
        {
            Vector2 origin = canvas.TopLeft() + _lineagePan;
            for (int e = 0; e < _lineage.Edges.Length; e++)
            {
                var edge = _lineage.Edges[e];
                Color edgeInk = _highlightEdges[e] ? new Color(151, 74, 35) : new Color(119, 94, 57);
                var visible = VisibleLineageSegments(edge.Path, (canvas.Top - origin.Y) / _lineageZoom, (canvas.Bottom - origin.Y) / _lineageZoom);
                for (int p = visible.Start; p < visible.End; p++)
                {
                    Vector2 from = origin + edge.Path[p-1] * _lineageZoom, to = origin + edge.Path[p] * _lineageZoom;
                    if (Math.Max(from.X, to.X) < canvas.Left || Math.Min(from.X, to.X) > canvas.Right
                        || Math.Max(from.Y, to.Y) < canvas.Top || Math.Min(from.Y, to.Y) > canvas.Bottom) continue;
                    Trace(sb, from, to, edgeInk);
                }
                if (visible.Start < visible.End && edge.Multiplicity > 1 && edge.Path.Length > 1)
                    LineageLabel(sb, _edgeMultiplicityLabels[e], origin + edge.Path[edge.Path.Length / 2] * _lineageZoom, MapInk, .6f * _lineageZoom, (int)(40 * _lineageZoom));
            }
            for (int i = 0; i < _lineage.Nodes.Length; i++)
            {
                var node = _lineage.Nodes[i]; Vector2 center = origin + node.Position * _lineageZoom;
                int radius = Math.Max(7, (int)(28 * _lineageZoom));
                var well = new Rectangle((int)center.X-radius,(int)center.Y-radius,radius*2,radius*2);
                if (!canvas.Intersects(new Rectangle(well.X-70, well.Y, well.Width+140, well.Height+35))) continue;
                DrawBookWell(sb, well, i == _lineage.RootIndex, i == hoverIndex);
                var icon = new Rectangle(well.X+radius/4,well.Y+radius/4,well.Width-radius/2,well.Height-radius/2);
                if (node.Data is not null) Sprite(sb, node.Data, icon);
                else if (_nativeNodes[i] is { } item) DrawNativeLineageSprite(sb, item, icon);
                else LineageCenterLabel(sb, "?", new Rectangle(well.X,well.Y+radius/2,well.Width,well.Height), MapInk, .8f * _lineageZoom);
                float scale = .6f * _lineageZoom;
                if (_lineageZoom >= .45f) sb.DrawString(FontAssets.MouseText.Value, _lineageCaptions[i],
                    new Vector2(center.X - _lineageCaptionWidths[i] * scale / 2, well.Bottom + 4), MapInk, 0, Vector2.Zero, scale, SpriteEffects.None, 0);
            }
        }
        finally
        {
            sb.End(); device.ScissorRectangle = oldScissor;
            sb.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, SamplerState.LinearClamp, DepthStencilState.None, oldRasterizer, null, Main.UIScaleMatrix);
        }
    }
    private static void DrawNativeLineageSprite(SpriteBatch sb, Item item, Rectangle rect)
    {
        Main.instance.LoadItem(item.type);
        Texture2D texture = TextureAssets.Item[item.type].Value;
        Rectangle frame = Main.itemAnimations[item.type]?.GetFrame(texture) ?? texture.Bounds;
        float scale = Math.Min(rect.Width/(float)frame.Width,rect.Height/(float)frame.Height);
        sb.Draw(texture,rect.Center.ToVector2(),frame,Color.White,0,frame.Size()*.5f,scale,SpriteEffects.None,0);
    }
    private static string ClipLineageLabel(string text, float width)
    {
        text = text.Replace('\r', ' ').Replace('\n', ' ');
        var font = FontAssets.MouseText.Value;
        if (font.MeasureString(text).X <= width) return text;
        while (text.Length > 0 && font.MeasureString(text + "…").X > width) text = text[..^1];
        return text + "…";
    }
    private static void LineageLabel(SpriteBatch sb, string text, Vector2 at, Color color, float scale, int width)
    {
        if (width <= 0) return;
        var font = FontAssets.MouseText.Value;
        text = text.Replace('\r', ' ').Replace('\n', ' ');
        if (font.MeasureString(text).X * scale > width)
        {
            while (text.Length > 0 && font.MeasureString(text + "…").X * scale > width) text = text[..^1];
            text += "…";
        }
        sb.DrawString(font, text, at, color, 0, Vector2.Zero, scale, SpriteEffects.None, 0);
    }
    private static void LineageCenterLabel(SpriteBatch sb, string text, Rectangle rect, Color color, float scale)
    {
        float width = Math.Min(rect.Width, FontAssets.MouseText.Value.MeasureString(text).X * scale);
        LineageLabel(sb, text, new Vector2(rect.X + (rect.Width - width) / 2, rect.Y), color, scale, rect.Width);
    }
    private static bool LineageButton(SpriteBatch sb, Rectangle rect, string text, bool click, Vector2 cursor)
    {
        bool hover = rect.Contains(cursor.ToPoint());
        Color brass = hover ? new Color(255, 224, 153) : new Color(199, 164, 91);
        LineageCenterLabel(sb, text, new Rectangle(rect.X, rect.Y + 3, rect.Width, rect.Height - 3), brass, .72f);
        if (hover) { Fill(sb, new Rectangle(rect.X + 5, rect.Bottom - 2, Math.Max(0, rect.Width - 10), 1), brass); _hoverText = text; }
        return hover && click;
    }
}
