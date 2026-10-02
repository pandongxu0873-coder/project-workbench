import io,sys
from PIL import Image
Image.MAX_IMAGE_PIXELS=4_000_000
raw=sys.stdin.buffer.read(3*1024*1024+1)
if len(raw)>3*1024*1024:raise ValueError('limit')
with Image.open(io.BytesIO(raw)) as im:
 if im.format not in {'PNG','JPEG','WEBP','ICO'} or im.width*im.height>4_000_000:raise ValueError('format')
 im.thumbnail((512,512));out=io.BytesIO();im.convert('RGBA').save(out,format='WEBP');sys.stdout.buffer.write(out.getvalue())
