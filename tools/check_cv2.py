import sys

try:
    import cv2
    print('cv2 OK', getattr(cv2, '__version__', '(no version)'))
    name = 'USB3 Video'
    try:
        cap = cv2.VideoCapture(f'dshow:video={name}')
        print('Attempting dshow open for device name:', name)
        print('dshow open ok?', cap.isOpened())
        if cap.isOpened():
            ret, frame = cap.read()
            print('read ret=', ret, 'frame is None=', frame is None)
            cap.release()
        else:
            print('dshow failed, trying index 0')
            cap2 = cv2.VideoCapture(0)
            print('index0 open ok?', cap2.isOpened())
            if cap2.isOpened():
                ret2, frame2 = cap2.read()
                print('index0 read ret=', ret2, 'frame None=', frame2 is None)
                cap2.release()
    except Exception as e:
        print('Error while opening capture device:', e)
except Exception as e:
    print('cv2 import failed:', e)
    sys.exit(0)
