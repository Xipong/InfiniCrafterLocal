"""Regression: sampled chroma background is not a global pink-material classifier."""
import json
from PIL import Image, ImageDraw
import pytest
from infini_local.pipelines.images import keyer, postprocess
from infini_local.pipelines.images.validation import validate_processed_sprite
from infini_local.services.visual_asset_pipeline import save_image_output, load_image_input


@pytest.mark.parametrize('rgb', [(249,93,166),(243,88,164),(241,101,169),(228,90,150),(215,95,156)])
def test_actual_rose_facets_are_not_key_evidence(rgb):
    im=Image.new('RGBA',(16,16));ImageDraw.Draw(im).rectangle((4,4,11,11),fill=rgb+(255,))
    assert keyer.magenta_key_pixel_ratio(im)==0
    cleaned=keyer.remove_key_colored_holes(im.copy(), {'key':(251,4,250),'tolerance':72})
    assert cleaned.tobytes()==im.tobytes()


@pytest.mark.parametrize('rgb',[(255,0,255),(250,8,249)])
def test_actual_key_square_and_enclosed_pocket_remain_detectable(rgb):
    im=Image.new('RGBA',(16,16));ImageDraw.Draw(im).rectangle((2,2,13,13),fill=(20,40,100,255))
    ImageDraw.Draw(im).rectangle((5,5,10,10),fill=rgb+(255,))
    assert keyer.magenta_key_pixel_ratio(im)>.025
    cleaned=keyer.remove_key_colored_holes(im,{'key':(251,4,250),'tolerance':72})
    assert cleaned.getpixel((7,7))[3]==0
    assert cleaned.getpixel((3,3))==(20,40,100,255)


def test_dark_sampled_key_receipt_survives_png_and_detects_residue(tmp_path):
    raw=Image.new('RGBA',(64,64),(202,4,140,255));ImageDraw.Draw(raw).rectangle((16,16,47,47),fill=(30,60,130,255))
    profile=keyer.estimate_sprite_key_profile(raw)
    assert profile['key']==(202,4,140)
    im=Image.new('RGBA',(32,32));ImageDraw.Draw(im).rectangle((6,6,25,25),fill=(30,60,130,255))
    ImageDraw.Draw(im).rectangle((12,12,19,19),fill=(202,4,140,255))
    im.info['infini.chroma-key']=json.dumps({'schema':'infini.sampled-chroma-key.v1',**profile})
    target=tmp_path/'dark.png';save_image_output(im,target)
    reopened=load_image_input(str(target),Image)
    assert keyer.magenta_key_pixel_ratio(reopened)>.025
    report=validate_processed_sprite(str(target),'projectile',expected_canvas=32)
    assert any(r.startswith('magenta_key_background_left') for r in report['reasons'])
    cleaned=keyer.remove_key_colored_holes(reopened,profile)
    assert cleaned.getpixel((15,15))[3]==0


def test_transparent_hidden_rgb_and_white_are_not_key_evidence():
    im=Image.new('RGBA',(16,16),(255,0,255,0));ImageDraw.Draw(im).rectangle((4,4,11,11),fill=(235,218,235,255))
    assert keyer.magenta_key_pixel_ratio(im)==0


def test_canonical_processing_preserves_rose_interior_and_boundary(tmp_path,monkeypatch):
    raw=Image.new('RGBA',(96,96),(251,4,250,255));draw=ImageDraw.Draw(raw)
    draw.rectangle((24,14,71,81),fill=(20,30,65,255));draw.rectangle((27,17,68,78),fill=(249,93,166,255))
    # Actual near-key fringe, separate from rose foreground by a dark outline.
    draw.line((23,14,23,81),fill=(250,8,249,255))
    raw.info['infini.chroma-key']='provider-supplied stale invalid receipt'
    path=tmp_path/'raw.png';save_image_output(raw,path)
    out=postprocess.postprocess_sprite(str(path),'rose',32,'projectile',output_dir=tmp_path/'processed',master_output=tmp_path/'master.png')
    master=load_image_input(str(tmp_path/'master.png'),Image)
    assert any(px[3] and px[:3]==(249,93,166) for px in master.getdata())
    final=load_image_input(out,Image)
    assert keyer.recorded_key_profile(final)['key']==[251,4,250]
    assert keyer.magenta_key_pixel_ratio(final)<=.025
    assert any(px[3] and px[0]>px[2]>px[1] for px in final.getdata())
    assert final.getpixel((0,0))[3]==0


def test_edge_cleanup_removes_real_fringe_not_distant_rose(monkeypatch):
    from infini_local.pipelines.images import pixels
    monkeypatch.setattr(pixels,'SPRITE_CHROMA_DEFRINGE',True)
    im=Image.new('RGBA',(16,16));d=ImageDraw.Draw(im)
    d.rectangle((4,4,11,11),fill=(20,30,65,255))
    im.putpixel((3,6),(250,8,249,255))
    im.putpixel((3,9),(249,93,166,255))
    cleaned=pixels.defringe_chroma_edges(im)
    assert cleaned.getpixel((3,6))[3]==0
    assert cleaned.getpixel((3,9))==(249,93,166,255)
    cleaned=pixels.neutralize_chroma_edge_colors(cleaned)
    assert cleaned.getpixel((3,9))==(249,93,166,255)


def test_invalid_sample_receipt_cannot_disable_validation(tmp_path):
    im=Image.new('RGBA',(32,32),(255,0,255,255));im.info['infini.chroma-key']='{"key":[999,0,999]}'
    path=tmp_path/'bad.png';save_image_output(im,path)
    with pytest.raises(ValueError,match='invalid sampled chroma-key'):
        keyer.magenta_key_pixel_ratio(load_image_input(str(path),Image))


def test_sample_receipt_never_disables_configured_key_detection():
    im=Image.new('RGBA',(16,16),(255,0,255,255))
    im.info['infini.chroma-key']=json.dumps({'schema':'infini.sampled-chroma-key.v1','key':[20,40,200],'tolerance':72,'samples':100,'source':'border_profile'})
    assert keyer.magenta_key_pixel_ratio(im)==1
