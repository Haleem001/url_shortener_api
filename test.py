import cloudinary.uploader
from django.conf import settings

def test_cloudinary():
    try:
        result = cloudinary.uploader.upload("https://via.placeholder.com/150", 
                                          public_id="test_upload")
        print("Cloudinary working:", result['secure_url'])
        return True
    except Exception as e:
        print("Cloudinary error:", str(e))
        return False
