"""Canvas padding must not manufacture successful provider background removal."""
from PIL import Image,ImageDraw
import pytest
from infini_local.core.images import config
from infini_local.pipelines.images import postprocess as post,validation


def source(tmp_path,background,pattern=False):
    im=Image.new('RGBA',(80,64),background);draw=ImageDraw.Draw(im)
    if pattern:
        for y in range(0,64,8):
            for x in range(0,80,8):
                draw.rectangle((x,y,x+7,y+7),fill=(195,195,195,255) if (x//8+y//8)%2 else (250,250,250,255))
    draw.rectangle((20,20,59,43),fill=(70,80,110,255))
    path=tmp_path/'raw.png';im.save(path);return path


@pytest.mark.parametrize('role',['item','runtime:projectile','runtime:child_projectile','vfx_cutout'])
@pytest.mark.parametrize('pattern',[False,True])
def test_opaque_wrong_matte_refused_before_fit(tmp_path,monkeypatch,role,pattern):
    monkeypatch.setattr(config,'BG_COLOR','magenta');path=source(tmp_path,(235,235,235,255),pattern)
    before=path.read_bytes()
    with pytest.raises(post.RawSpriteBackgroundError,match='raw_background_not_removed'):
        post.postprocess_sprite(str(path),'bad',32,role,output_dir=tmp_path/'out')
    assert path.read_bytes()==before
    assert not (tmp_path/'out/bad.png').exists()


@pytest.mark.parametrize('foreground',[(255,255,255,255),(150,150,150,255)])
def test_rectangle_white_gray_object_on_true_key_allowed(tmp_path,monkeypatch,foreground):
    monkeypatch.setattr(config,'BG_COLOR','magenta');im=Image.new('RGBA',(80,64),(255,0,255,255));ImageDraw.Draw(im).rectangle((12,12,67,51),fill=foreground)
    path=tmp_path/'key.png';im.save(path)
    result=post.postprocess_sprite(str(path),'good',32,'runtime:projectile',output_dir=tmp_path/'out')
    assert validation.validate_processed_sprite(result,'runtime:projectile',expected_canvas=32)['ok']


@pytest.mark.parametrize('background',['transparent','magenta'])
def test_real_alpha_with_checker_inside_object_allowed(tmp_path,monkeypatch,background):
    monkeypatch.setattr(config,'BG_COLOR',background);im=Image.new('RGBA',(64,64));d=ImageDraw.Draw(im)
    for y in range(16,48,8):
        for x in range(16,48,8):d.rectangle((x,y,x+7,y+7),fill=(180,180,180,255) if (x//8+y//8)%2 else (250,250,250,255))
    path=tmp_path/'pattern.png';im.save(path)
    result=post.postprocess_sprite(str(path),'good',32,'runtime:projectile',output_dir=tmp_path/'out')
    assert validation.validate_processed_sprite(result,'runtime:projectile',expected_canvas=32)['ok']


def test_full_frame_strip_policy_unchanged(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'BG_COLOR','transparent');im=Image.new('RGBA',(32,32),(160,180,220,180));path=tmp_path/'strip.png';im.save(path)
    result=post.postprocess_sprite(str(path),'strip',32,'vfx_strip',output_dir=tmp_path/'out')
    assert Image.open(result).size==(32,32)
    assert validation.validate_processed_sprite(result,'vfx_strip',expected_canvas=32)['ok']


def test_enclosed_transparent_hole_is_not_background_removal(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'BG_COLOR','magenta')
    path=source(tmp_path,(235,235,235,255),True)
    raw=Image.open(path).convert('RGBA');ImageDraw.Draw(raw).rectangle((24,24,55,39),fill=(255,0,255,255));raw.save(path)
    with pytest.raises(post.RawSpriteBackgroundError,match='exterior transparency'):
        post.postprocess_sprite(str(path),'false-hole',32,'runtime:projectile',output_dir=tmp_path/'out')
    assert not (tmp_path/'out/false-hole.png').exists()


def fail_before_background_guard(*args, **kwargs):
    raise RuntimeError("injected technical processing error before exterior guard")


@pytest.mark.parametrize('fault_owner',['apply_background_removal','defringe_chroma_edges','prepare_sprite_master','bake_sprite_from_master'])
def test_real_exterior_alpha_still_supports_technical_rescue(tmp_path,monkeypatch,fault_owner):
    monkeypatch.setattr(config,'BG_COLOR','magenta')
    im=Image.new('RGBA',(80,64));ImageDraw.Draw(im).rectangle((6,16,73,47),fill=(70,80,110,255))
    path=tmp_path/'alpha.png';im.save(path)
    before=path.read_bytes()
    monkeypatch.setattr(post,fault_owner,fail_before_background_guard)
    result=post.postprocess_sprite(str(path),'rescued',32,'runtime:projectile',output_dir=tmp_path/'out')
    assert validation.validate_processed_sprite(result,'runtime:projectile',expected_canvas=32)['ok']
    assert path.read_bytes()==before


@pytest.mark.parametrize('fault_owner',['apply_background_removal','defringe_chroma_edges'])
def test_wrong_matte_with_enclosed_hole_cannot_escape_through_rescue(tmp_path,monkeypatch,fault_owner):
    monkeypatch.setattr(config,'BG_COLOR','magenta')
    path=source(tmp_path,(235,235,235,255),True)
    raw=Image.open(path).convert('RGBA')
    ImageDraw.Draw(raw).rectangle((24,24,55,39),fill=(255,0,255,255))
    raw.save(path); before=path.read_bytes()
    monkeypatch.setattr(post,fault_owner,fail_before_background_guard)
    with pytest.raises(post.RawSpriteBackgroundError,match='exterior transparency before rescue'):
        post.postprocess_sprite(str(path),'bad-rescue',32,'runtime:projectile',output_dir=tmp_path/'out')
    assert path.read_bytes()==before
    assert not (tmp_path/'out/bad-rescue.png').exists()
