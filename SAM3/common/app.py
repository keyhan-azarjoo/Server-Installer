"""
SAM3 Professional Dashboard - Flask Web Application

This is the main Flask application file that handles web requests.
All business logic is separated into the 'core' module.
All frontend files are in the 'web' folder.

Project Structure:
    - core/          : Backend functions and detection logic
    - web/           : Frontend files (templates, static assets)
    - app.py         : This file - Flask routes and web server
"""

import io
import os
import sys
import time

# Ensure UTF-8 output on all platforms (prevents emoji UnicodeEncodeError on Windows)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import numpy as np
from flask import Flask, request, render_template, jsonify, Response
from PIL import Image

# Import core backend modules
from core.detector import SAM3Detector, get_best_device
from core.utils import to_base64
from core.tracker import add_tracking, match_tracked_object


# ====================================
# Flask App Configuration
# ====================================

app = Flask(
    __name__,
    template_folder=os.path.join('web', 'templates'),
    static_folder=os.path.join('web', 'static')
)


# ====================================
# Initialize SAM3 Detector
# ====================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.environ.get("SAM3_MODEL_PATH", os.path.join(BASE_DIR, "sam3.pt"))
# Also check models/ subdirectory as fallback
if not os.path.exists(MODEL_PATH):
    alt = os.path.join(BASE_DIR, "models", "sam3.pt")
    if os.path.exists(alt):
        MODEL_PATH = alt
TEMP_VIDEO_DIR = os.path.join(BASE_DIR, "temp", "videos")
DEVICE = os.environ.get("SAM3_DEVICE", get_best_device())

# Create detector instance (loads model once at startup)
# If model file is missing, detector will fail gracefully on first request
detector = None
if os.path.exists(MODEL_PATH):
    try:
        detector = SAM3Detector(
            model_path=MODEL_PATH,
            device=DEVICE,
            default_conf=0.25
        )
        print(f"Model loaded: {MODEL_PATH} on {DEVICE}")
    except Exception as e:
        print(f"Warning: Could not load model: {e}")
else:
    print(f"Warning: Model file not found at {MODEL_PATH}. Download it first.")


# ====================================
# Routes
# ====================================

def _ensure_detector():
    """Check if detector is loaded; return error response if not."""
    global detector
    if detector is not None:
        return None
    # Try to load now (model may have been downloaded after startup)
    if os.path.exists(MODEL_PATH):
        try:
            detector = SAM3Detector(model_path=MODEL_PATH, device=DEVICE, default_conf=0.25)
            print(f"Model loaded on demand: {MODEL_PATH}")
            return None
        except Exception as e:
            return jsonify({"error": f"Model loading failed: {e}"}), 500
    return jsonify({"error": f"Model not found at {MODEL_PATH}. Download sam3.pt first."}), 503


@app.route("/", methods=["GET"])
def index():
    """
    Main dashboard page.
    Serves the professional Bootstrap-based UI.
    """
    return render_template("index.html")


@app.route("/detect", methods=["POST"])
def detect():
    """
    AJAX endpoint for object detection with individual layer support.

    Accepts:
        - image: Image file upload
        - text_prompt: Text description of object to detect
        - confidence: Detection confidence threshold (optional)

    Returns:
        JSON response with individual object layers and metadata
    """
    try:
        err = _ensure_detector()
        if err: return err
        # Get form data
        file = request.files.get("image")
        text_prompt = request.form.get("text_prompt", "").strip()
        confidence = float(request.form.get("confidence", 0.25))

        # Validate inputs
        if not file:
            return jsonify({"error": "No image file provided"}), 400
        if not text_prompt:
            return jsonify({"error": "No text prompt provided"}), 400

        # Load image
        image = Image.open(file.stream).convert("RGB")

        # Run detection using core detector module
        results = detector.detect(
            image=image,
            text_prompt=text_prompt,
            confidence=confidence
        )

        # Calculate average confidence from objects
        confidence_scores = [obj['confidence'] for obj in results['objects'] if obj['confidence'] is not None]
        avg_confidence = "N/A"
        if confidence_scores:
            avg_conf_value = sum(confidence_scores) / len(confidence_scores)
            avg_confidence = f"{avg_conf_value:.2%}"

        # Prepare response with individual objects
        response_data = {
            "original": to_base64(results['original_image']),
            "image_size": results['image_size'],
            "objects": results['objects'],  # Individual object data
            "stats": {
                "objects_detected": results['objects_detected'],
                "processing_time": f"{results['processing_time']:.2f}s",
                "avg_confidence": avg_confidence
            }
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Error during detection: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Detection failed: {str(e)}"}), 500


@app.route("/detect-live", methods=["POST"])
def detect_live():
    """
    Lightweight detection endpoint for live camera frames.
    Returns bounding boxes and labels only (no masks) for real-time speed.

    Accepts:
        - image: JPEG frame from camera
        - text_prompt: Text description of objects to detect
        - confidence: Detection confidence threshold (optional)

    Returns:
        JSON with objects (bbox + label + confidence only), processing_time
    """
    try:
        err = _ensure_detector()
        if err: return err
        file = request.files.get("image")
        text_prompt = request.form.get("text_prompt", "").strip()
        confidence = float(request.form.get("confidence", 0.25))
        grid_mode = request.form.get("grid_mode", "off")
        quality = int(request.form.get("quality", 50))

        if not file:
            return jsonify({"error": "No image provided"}), 400
        if not text_prompt:
            return jsonify({"error": "No text prompt provided"}), 400

        # Map quality % to SAM3 inference size (same as video processor)
        imgsz_map = {25: 320, 50: 480, 75: 640, 100: 800}
        imgsz = imgsz_map.get(quality, 480)

        image = Image.open(file.stream).convert("RGB")

        # Check if click-to-track is active (need contours for shape display)
        track_x = request.form.get("track_x")
        track_y = request.form.get("track_y")
        is_tracking = track_x is not None and track_y is not None

        # Use lightweight detect method (contours only when tracking)
        results = detector.detect_live(
            image=image,
            text_prompt=text_prompt,
            confidence=confidence,
            imgsz=imgsz,
            return_contours=is_tracking,
        )

        img_w = results['image_size']['width']
        img_h = results['image_size']['height']

        # Add position tracking if enabled (logic lives in core/tracker.py)
        if grid_mode != "off":
            add_tracking(results['objects'], img_w, img_h, grid_mode)

        # Click-to-track: match a specific object across frames
        tracked = None
        if is_tracking:
            tracked = match_tracked_object(
                results['objects'],
                target_center={'x': float(track_x), 'y': float(track_y)},
                img_width=img_w,
                img_height=img_h,
                grid_mode=grid_mode if grid_mode != "off" else "3",
            )
            # Copy contour from matched object into tracked response
            if tracked:
                matched_id = tracked['id']
                for obj in results['objects']:
                    if obj.get('id') == matched_id:
                        tracked['contour'] = obj.get('contour', [])
                        break

        # Strip contours from all objects (only needed in tracked response)
        for obj in results['objects']:
            obj.pop('contour', None)

        return jsonify({
            "objects": results['objects'],
            "objects_detected": results['objects_detected'],
            "processing_time": results['processing_time'],
            "image_size": results['image_size'],
            "tracked": tracked,
        })

    except Exception as e:
        print(f"❌ Error during live detection: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Live detection failed: {str(e)}"}), 500


@app.route("/detect-point", methods=["POST"])
def detect_point():
    """
    AJAX endpoint for point-based object detection.

    Accepts:
        - image: Image file upload
        - points: JSON string of point coordinates [[x1,y1], [x2,y2], ...]
        - labels: JSON string of labels [1, 0, 1, ...] (1=foreground, 0=background)
        - confidence: Detection confidence threshold (optional)

    Returns:
        JSON response with individual object layers and metadata
    """
    try:
        err = _ensure_detector()
        if err: return err
        import json

        # Get form data
        file = request.files.get("image")
        points_json = request.form.get("points", "[]")
        labels_json = request.form.get("labels", "[]")
        confidence = float(request.form.get("confidence", 0.25))

        # Validate inputs
        if not file:
            return jsonify({"error": "No image file provided"}), 400

        # Parse JSON
        points = json.loads(points_json)
        labels = json.loads(labels_json)

        if not points or not labels:
            return jsonify({"error": "No points or labels provided"}), 400

        if len(points) != len(labels):
            return jsonify({"error": "Points and labels must have same length"}), 400

        # Load image
        image = Image.open(file.stream).convert("RGB")

        # Run detection using point prompts
        results = detector.detect_by_points(
            image=image,
            points=points,
            labels=labels,
            confidence=confidence
        )

        # Calculate average confidence from objects
        confidence_scores = [obj['confidence'] for obj in results['objects'] if obj['confidence'] is not None]
        avg_confidence = "N/A"
        if confidence_scores:
            avg_conf_value = sum(confidence_scores) / len(confidence_scores)
            avg_confidence = f"{avg_conf_value:.2%}"

        # Prepare response with individual objects
        response_data = {
            "original": to_base64(results['original_image']),
            "image_size": results['image_size'],
            "objects": results['objects'],  # Individual object data
            "stats": {
                "objects_detected": results['objects_detected'],
                "processing_time": f"{results['processing_time']:.2f}s",
                "avg_confidence": avg_confidence
            }
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Error during point detection: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Detection failed: {str(e)}"}), 500


@app.route("/detect-box", methods=["POST"])
def detect_box():
    """
    AJAX endpoint for bounding-box-based object detection.

    Accepts:
        - image: Image file upload
        - bboxes: JSON string [[x_min, y_min, x_max, y_max], ...]
        - confidence: Detection confidence threshold (optional)
    """
    try:
        err = _ensure_detector()
        if err: return err
        import json

        file = request.files.get("image")
        bboxes_json = request.form.get("bboxes", "[]")
        confidence = float(request.form.get("confidence", 0.25))

        if not file:
            return jsonify({"error": "No image file provided"}), 400

        bboxes = json.loads(bboxes_json)
        if not bboxes:
            return jsonify({"error": "No bounding boxes provided"}), 400

        image = Image.open(file.stream).convert("RGB")

        results = detector.detect_by_box(
            image=image,
            bboxes=bboxes,
            confidence=confidence
        )

        confidence_scores = [obj['confidence'] for obj in results['objects'] if obj['confidence'] is not None]
        avg_confidence = "N/A"
        if confidence_scores:
            avg_confidence = f"{sum(confidence_scores) / len(confidence_scores):.2%}"

        response_data = {
            "original": to_base64(results['original_image']),
            "image_size": results['image_size'],
            "objects": results['objects'],
            "stats": {
                "objects_detected": results['objects_detected'],
                "processing_time": f"{results['processing_time']:.2f}s",
                "avg_confidence": avg_confidence
            }
        }
        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Error during box detection: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Detection failed: {str(e)}"}), 500


@app.route("/detect-exemplar", methods=["POST"])
def detect_exemplar():
    """
    AJAX endpoint for exemplar-based (visual reference) object detection.

    Accepts:
        - image: Image file upload
        - reference_bbox: JSON string [x_min, y_min, x_max, y_max]
        - confidence: Detection confidence threshold (optional)
    """
    try:
        err = _ensure_detector()
        if err: return err
        import json

        file = request.files.get("image")
        ref_bbox_json = request.form.get("reference_bbox", "[]")
        confidence = float(request.form.get("confidence", 0.25))

        if not file:
            return jsonify({"error": "No image file provided"}), 400

        reference_bbox = json.loads(ref_bbox_json)
        if not reference_bbox or len(reference_bbox) != 4:
            return jsonify({"error": "Invalid reference bounding box"}), 400

        image = Image.open(file.stream).convert("RGB")

        results = detector.detect_by_exemplar(
            image=image,
            reference_bbox=reference_bbox,
            confidence=confidence
        )

        confidence_scores = [obj['confidence'] for obj in results['objects'] if obj['confidence'] is not None]
        avg_confidence = "N/A"
        if confidence_scores:
            avg_confidence = f"{sum(confidence_scores) / len(confidence_scores):.2%}"

        response_data = {
            "original": to_base64(results['original_image']),
            "image_size": results['image_size'],
            "objects": results['objects'],
            "clip_label": results.get('clip_label'),
            "clip_score": results.get('clip_score'),
            "stats": {
                "objects_detected": results['objects_detected'],
                "processing_time": f"{results['processing_time']:.2f}s",
                "avg_confidence": avg_confidence,
                "clip_label": results.get('clip_label'),
                "clip_score": f"{results.get('clip_score', 0):.1%}" if results.get('clip_score') else "N/A"
            }
        }
        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Error during exemplar detection: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Detection failed: {str(e)}"}), 500


@app.route("/export/mask", methods=["POST"])
def export_mask():
    """
    Export a single object mask as PNG.

    Accepts JSON:
        - image_base64: base64-encoded original image
        - object: object dict with mask, color, label
    """
    try:
        import json
        import base64
        from flask import send_file
        from core.exporter import MaskExporter

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Decode image
        img_data = base64.b64decode(data['image_base64'])
        image = Image.open(io.BytesIO(img_data)).convert("RGB")
        image_np = np.array(image)

        obj = data['object']
        png_bytes = MaskExporter.export_single_mask_png(obj, image_np)

        label = obj.get('label', 'mask').replace(' ', '_').replace('#', '')
        return send_file(
            io.BytesIO(png_bytes),
            mimetype='image/png',
            as_attachment=True,
            download_name=f"{label}.png"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export/masks-zip", methods=["POST"])
def export_masks_zip():
    """
    Export all object masks as a ZIP of PNG files.

    Accepts JSON:
        - image_base64: base64-encoded original image
        - objects: list of object dicts
    """
    try:
        import base64
        from flask import send_file
        from core.exporter import MaskExporter

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        img_data = base64.b64decode(data['image_base64'])
        image = Image.open(io.BytesIO(img_data)).convert("RGB")
        image_np = np.array(image)

        objects = data['objects']
        zip_bytes = MaskExporter.export_all_masks_zip(objects, image_np)

        return send_file(
            io.BytesIO(zip_bytes),
            mimetype='application/zip',
            as_attachment=True,
            download_name='masks.zip'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export/json", methods=["POST"])
def export_json_file():
    """
    Export detection results as JSON.

    Accepts JSON body with detection_results dict.
    """
    try:
        from flask import send_file
        from core.exporter import MaskExporter

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        json_bytes = MaskExporter.export_json(data)

        return send_file(
            io.BytesIO(json_bytes),
            mimetype='application/json',
            as_attachment=True,
            download_name='detections.json'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export/coco", methods=["POST"])
def export_coco():
    """
    Export detection results in COCO format.

    Accepts JSON body with detection_results dict.
    """
    try:
        from flask import send_file
        from core.exporter import MaskExporter

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        image_filename = data.pop('image_filename', 'image.jpg')
        json_bytes = MaskExporter.export_coco(data, image_filename=image_filename)

        return send_file(
            io.BytesIO(json_bytes),
            mimetype='application/json',
            as_attachment=True,
            download_name='coco_annotations.json'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/upload-video", methods=["POST"])
def upload_video():
    """
    Upload video file and return video metadata.

    Accepts:
        - video: Video file (MP4, AVI, MOV, WebM)

    Returns:
        JSON with video_id and metadata
    """
    try:
        from core.video_processor import SAM3VideoProcessor

        # Get uploaded file
        file = request.files.get("video")
        if not file:
            return jsonify({"error": "No video file provided"}), 400

        # Validate file extension
        allowed_extensions = {'.mp4', '.avi', '.mov', '.webm'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({"error": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"}), 400

        # Initialize video processor
        video_processor = SAM3VideoProcessor(
            model_path=MODEL_PATH,
            device=DEVICE,
            temp_dir=TEMP_VIDEO_DIR
        )

        # Save video
        video_info = video_processor.save_uploaded_video(file, file.filename)
        video_id = video_info['video_id']
        video_path = video_info['video_path']

        # Get video metadata
        metadata = video_processor.get_video_info(video_path)

        # Store video path in session or cache (using simple dict for now)
        if not hasattr(app, 'video_paths'):
            app.video_paths = {}
        app.video_paths[video_id] = video_path

        response_data = {
            'video_id': video_id,
            'duration': metadata['duration'],
            'fps': metadata['fps'],
            'frame_count': metadata['frame_count'],
            'resolution': metadata['resolution']
        }

        return jsonify(response_data)

    except Exception as e:
        print(f"❌ Error during video upload: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Video upload failed: {str(e)}"}), 500


@app.route("/process-video/<video_id>", methods=["GET"])
def process_video(video_id):
    """
    Process video with Server-Sent Events for real-time progress.

    Query params:
        - text_prompt: Comma-separated text prompts
        - confidence: Detection confidence (default 0.25)

    Returns:
        SSE stream with progress, frame, and complete events
    """
    try:
        import json
        from core.video_processor import SAM3VideoProcessor

        # Get video path from memory or reconstruct from disk
        video_path = None

        if hasattr(app, 'video_paths') and video_id in app.video_paths:
            video_path = app.video_paths[video_id]
        else:
            # Try to find video file on disk (in case app restarted)
            temp_dir = TEMP_VIDEO_DIR
            if os.path.exists(temp_dir):
                for filename in os.listdir(temp_dir):
                    if filename.startswith(video_id):
                        video_path = os.path.join(temp_dir, filename)
                        break

        if not video_path or not os.path.exists(video_path):
            return jsonify({"error": "Video not found"}), 404

        # Get query parameters
        text_prompt = request.args.get('text_prompt', '').strip()
        confidence = float(request.args.get('confidence', 0.25))
        process_fps = int(request.args.get('process_fps', 10))
        quality_scale = int(request.args.get('quality_scale', 50))

        if not text_prompt:
            return jsonify({"error": "No text prompt provided"}), 400

        # Initialize video processor
        video_processor = SAM3VideoProcessor(
            model_path=MODEL_PATH,
            device=DEVICE,
            temp_dir=TEMP_VIDEO_DIR
        )

        def generate():
            """Generator function for SSE"""
            try:
                start_time = time.time()
                frame_count = 0

                # Process video frames using SAM3VideoSemanticPredictor
                for frame_data in video_processor.process_video(
                    video_path=video_path,
                    text_prompts=text_prompt,
                    confidence=confidence,
                    process_fps=process_fps,
                    quality_scale=quality_scale
                ):
                    # Send progress event
                    progress_data = {
                        'frame': frame_count + 1,
                        'total': 'processing...',
                        'progress': frame_data['progress']
                    }
                    yield f"event: progress\ndata: {json.dumps(progress_data)}\n\n"

                    frame_count += 1

                    # Send frame event
                    yield f"event: frame\ndata: {json.dumps(frame_data)}\n\n"

                # Send completion event
                processing_time = time.time() - start_time
                complete_data = {
                    'total_frames': frame_count,
                    'processing_time': processing_time,
                    'video_id': video_id  # Send video_id so frontend can load the video
                }
                yield f"event: complete\ndata: {json.dumps(complete_data)}\n\n"

                # Don't cleanup video file yet - we need it for playback
                # It will be cleaned up when user uploads a new video or after timeout

            except Exception as e:
                error_data = {'error': str(e)}
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"

        return Response(generate(), mimetype='text/event-stream')

    except Exception as e:
        print(f"❌ Error during video processing: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Video processing failed: {str(e)}"}), 500


@app.route("/get-video/<video_id>", methods=["GET"])
def get_video(video_id):
    """
    Serve the video file for playback.

    Returns:
        Video file stream
    """
    try:
        from flask import send_file

        # Get video path
        video_path = None

        if hasattr(app, 'video_paths') and video_id in app.video_paths:
            video_path = app.video_paths[video_id]
        else:
            # Try to find video file on disk
            temp_dir = TEMP_VIDEO_DIR
            if os.path.exists(temp_dir):
                for filename in os.listdir(temp_dir):
                    if filename.startswith(video_id):
                        video_path = os.path.join(temp_dir, filename)
                        break

        if not video_path or not os.path.exists(video_path):
            return jsonify({"error": "Video not found"}), 404

        # Serve the video file
        return send_file(video_path, mimetype='video/mp4')

    except Exception as e:
        print(f"❌ Error serving video: {str(e)}")
        return jsonify({"error": f"Failed to serve video: {str(e)}"}), 500


@app.route("/get-frame/<video_id>/<int:frame_number>", methods=["GET"])
def get_frame(video_id, frame_number):
    """
    Extract and serve a single video frame as JPEG.
    Used by the Object Tracker to let users select an object on a specific frame.
    """
    try:
        from flask import send_file
        from core.video_processor import SAM3VideoProcessor

        video_path = None
        if hasattr(app, 'video_paths') and video_id in app.video_paths:
            video_path = app.video_paths[video_id]
        else:
            temp_dir = TEMP_VIDEO_DIR
            if os.path.exists(temp_dir):
                for filename in os.listdir(temp_dir):
                    if filename.startswith(video_id):
                        video_path = os.path.join(temp_dir, filename)
                        break

        if not video_path or not os.path.exists(video_path):
            return jsonify({"error": "Video not found"}), 404

        vp = SAM3VideoProcessor(model_path=MODEL_PATH, device=DEVICE, temp_dir=TEMP_VIDEO_DIR)
        jpeg_bytes = vp.get_frame_as_jpeg(video_path, frame_number)

        return send_file(io.BytesIO(jpeg_bytes), mimetype='image/jpeg')

    except Exception as e:
        print(f"❌ Error extracting frame: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/track-object/<video_id>", methods=["GET"])
def track_object(video_id):
    """
    Track a specific object across video frames using SSE.

    Query params:
        - frame_number: Starting frame where object is selected
        - bbox: JSON [x_min, y_min, x_max, y_max]
        - confidence: Detection confidence (default 0.25)
        - quality_scale: 5/10/25/50/75/100 (default 50)
    """
    try:
        import json as _json
        from core.video_processor import SAM3VideoProcessor

        frame_number = int(request.args.get("frame_number", 0))
        bbox_json = request.args.get("bbox", "[]")
        confidence = float(request.args.get("confidence", 0.25))
        quality_scale = int(request.args.get("quality_scale", 50))

        bbox = _json.loads(bbox_json)
        if len(bbox) != 4:
            return jsonify({"error": "bbox must be [x_min, y_min, x_max, y_max]"}), 400

        video_path = None
        if hasattr(app, 'video_paths') and video_id in app.video_paths:
            video_path = app.video_paths[video_id]
        else:
            temp_dir = TEMP_VIDEO_DIR
            if os.path.exists(temp_dir):
                for filename in os.listdir(temp_dir):
                    if filename.startswith(video_id):
                        video_path = os.path.join(temp_dir, filename)
                        break

        if not video_path or not os.path.exists(video_path):
            return jsonify({"error": "Video not found"}), 404

        def generate():
            try:
                vp = SAM3VideoProcessor(model_path=MODEL_PATH, device=DEVICE, temp_dir=TEMP_VIDEO_DIR)
                start_time = time.time()
                total_count = 0

                for frame_result in vp.track_object(
                    video_path=video_path,
                    start_frame=frame_number,
                    bbox=bbox,
                    confidence=confidence,
                    quality_scale=quality_scale
                ):
                    yield f"event: frame\ndata: {_json.dumps(frame_result)}\n\n"
                    total_count += 1

                complete_data = {
                    'total_frames': total_count,
                    'processing_time': time.time() - start_time,
                    'video_id': video_id
                }
                yield f"event: complete\ndata: {_json.dumps(complete_data)}\n\n"

            except Exception as e:
                yield f"event: error\ndata: {_json.dumps({'error': str(e)})}\n\n"

        return Response(generate(), mimetype='text/event-stream')

    except Exception as e:
        print(f"❌ Error during object tracking: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Object tracking failed: {str(e)}"}), 500


@app.route("/model-info", methods=["GET"])
def model_info():
    """
    Get information about the loaded SAM3 model.

    Returns:
        JSON with model configuration details
    """
    err = _ensure_detector()
    if err: return err
    info = detector.get_model_info()
    return jsonify(info)


# ====================================
# Run Server
# ====================================

if __name__ == "__main__":
    # Pre-load model at startup (non-fatal — web UI works without model)
    if os.path.exists(MODEL_PATH):
        try:
            detector = SAM3Detector(model_path=MODEL_PATH, device=DEVICE, default_conf=0.25)
            print(f"Model loaded: {MODEL_PATH}")
        except Exception as e:
            print(f"Warning: Model loading failed: {e}")
            print("The web UI will still start — you can download the model from the dashboard.")
    else:
        print(f"Note: Model not found at {MODEL_PATH}")
        print("The web UI will start without a model. Use the dashboard to download sam3.pt.")

    print("\n" + "="*50)
    print("SAM3 Professional Dashboard")
    print("="*50)
    print(f"Templates: {app.template_folder}")
    print(f"Static: {app.static_folder}")
    print(f"Model: {os.path.basename(MODEL_PATH)} ({'loaded' if detector else 'NOT LOADED'})")
    print(f"Device: {DEVICE}")
    print("="*50 + "\n")

    port = int(os.environ.get("SAM3_PORT", "5000"))
    https_port = os.environ.get("SAM3_HTTPS_PORT", "").strip()

    # Start HTTPS server in a separate thread if configured
    if https_port and https_port.isdigit() and int(https_port) > 0:
        import ssl
        import threading
        cert_dir = os.environ.get("SAM3_CERT_DIR", "/app/certs")
        cert_file = os.path.join(cert_dir, "sam3.crt")
        key_file = os.path.join(cert_dir, "sam3.key")
        # Auto-generate self-signed cert if not exists
        if not os.path.exists(cert_file):
            os.makedirs(cert_dir, exist_ok=True)
            try:
                import subprocess
                subprocess.run([
                    "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
                    "-keyout", key_file, "-out", cert_file, "-days", "3650",
                    "-subj", "/CN=SAM3/O=ServerInstaller/C=US"
                ], capture_output=True, timeout=30)
                print(f"Self-signed SSL cert created at {cert_file}")
            except Exception as e:
                print(f"Could not create SSL cert: {e}")
                https_port = ""
        if https_port and os.path.exists(cert_file) and os.path.exists(key_file):
            def run_https():
                try:
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                    ctx.load_cert_chain(cert_file, key_file)
                    from werkzeug.serving import make_server
                    srv = make_server("0.0.0.0", int(https_port), app, ssl_context=ctx, threaded=True)
                    print(f"HTTPS server on port {https_port}")
                    srv.serve_forever()
                except Exception as e:
                    print(f"HTTPS failed: {e}")
            threading.Thread(target=run_https, daemon=True).start()

    print(f"HTTP server on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
