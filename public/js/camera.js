/**
 * Camera Module
 *
 * Handles camera capture, device selection, and video stream management.
 */

export class Camera {
  constructor() {
    this.videoElement = null;
    this.stream = null;
    this.devices = [];
    this.currentDeviceId = null;
    this.isRunning = false;

    // Callbacks
    this.onFrame = null;
    this.onError = null;
    this.onDevicesChanged = null;

    // Frame capture settings
    this.captureWidth = 320;
    this.captureHeight = 240;
    this.frameRate = 15; // fps for motion detection

    // Hidden canvas for frame capture
    this.canvas = document.createElement('canvas');
    this.canvas.width = this.captureWidth;
    this.canvas.height = this.captureHeight;
    this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });

    this.frameInterval = null;
  }

  /**
   * Initialize the camera system.
   * @param {HTMLVideoElement} videoElement - Video element for preview
   */
  async init(videoElement) {
    this.videoElement = videoElement;

    // Listen for device changes (camera plugged/unplugged)
    navigator.mediaDevices.addEventListener('devicechange', () => {
      this.refreshDevices();
    });

    // Get initial device list
    await this.refreshDevices();
  }

  /**
   * Refresh the list of available camera devices.
   */
  async refreshDevices() {
    try {
      const allDevices = await navigator.mediaDevices.enumerateDevices();
      this.devices = allDevices.filter((d) => d.kind === 'videoinput');

      if (this.onDevicesChanged) {
        this.onDevicesChanged(this.devices);
      }

      return this.devices;
    } catch (error) {
      console.error('[Camera] Failed to enumerate devices:', error);
      return [];
    }
  }

  /**
   * Get list of available camera devices.
   */
  getDevices() {
    return this.devices;
  }

  /**
   * Start the camera with optional device ID.
   * @param {string} deviceId - Optional specific device to use
   */
  async start(deviceId = null) {
    if (this.isRunning) {
      await this.stop();
    }

    try {
      const constraints = {
        video: {
          width: { ideal: this.captureWidth },
          height: { ideal: this.captureHeight },
          frameRate: { ideal: this.frameRate },
        },
        audio: false,
      };

      // Add device constraint if specified
      if (deviceId) {
        constraints.video.deviceId = { exact: deviceId };
      }

      console.log('[Camera] Requesting camera access...');
      this.stream = await navigator.mediaDevices.getUserMedia(constraints);

      // Get actual device ID being used
      const videoTrack = this.stream.getVideoTracks()[0];
      if (videoTrack) {
        const settings = videoTrack.getSettings();
        this.currentDeviceId = settings.deviceId;
        console.log(`[Camera] Using device: ${videoTrack.label}`);
      }

      // Attach stream to video element
      if (this.videoElement) {
        this.videoElement.srcObject = this.stream;
        await this.videoElement.play();
      }

      this.isRunning = true;

      // Start frame capture loop
      this.startFrameCapture();

      // Refresh device list (labels become available after permission granted)
      await this.refreshDevices();

      return true;
    } catch (error) {
      console.error('[Camera] Failed to start:', error);

      if (this.onError) {
        if (error.name === 'NotAllowedError') {
          this.onError({
            type: 'permission_denied',
            message: 'Camera permission was denied',
          });
        } else if (error.name === 'NotFoundError') {
          this.onError({
            type: 'not_found',
            message: 'No camera found',
          });
        } else {
          this.onError({
            type: 'unknown',
            message: error.message,
          });
        }
      }

      return false;
    }
  }

  /**
   * Stop the camera.
   */
  async stop() {
    this.stopFrameCapture();

    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }

    if (this.videoElement) {
      this.videoElement.srcObject = null;
    }

    this.isRunning = false;
    this.currentDeviceId = null;

    console.log('[Camera] Stopped');
  }

  /**
   * Switch to a different camera device.
   * @param {string} deviceId - Device ID to switch to
   */
  async switchDevice(deviceId) {
    if (deviceId === this.currentDeviceId) return;

    console.log(`[Camera] Switching to device: ${deviceId}`);
    await this.start(deviceId);
  }

  /**
   * Start the frame capture loop.
   */
  startFrameCapture() {
    if (this.frameInterval) return;

    const intervalMs = 1000 / this.frameRate;

    this.frameInterval = setInterval(() => {
      if (this.isRunning && this.videoElement && this.onFrame) {
        this.captureFrame();
      }
    }, intervalMs);

    console.log(`[Camera] Frame capture started at ${this.frameRate} fps`);
  }

  /**
   * Stop the frame capture loop.
   */
  stopFrameCapture() {
    if (this.frameInterval) {
      clearInterval(this.frameInterval);
      this.frameInterval = null;
    }
  }

  /**
   * Capture a single frame and send to callback.
   */
  captureFrame() {
    if (!this.videoElement || this.videoElement.readyState < 2) return;

    // Draw video frame to canvas
    this.ctx.drawImage(
      this.videoElement,
      0,
      0,
      this.captureWidth,
      this.captureHeight
    );

    // Get image data
    const imageData = this.ctx.getImageData(
      0,
      0,
      this.captureWidth,
      this.captureHeight
    );

    // Send to callback
    if (this.onFrame) {
      this.onFrame({
        imageData,
        width: this.captureWidth,
        height: this.captureHeight,
        timestamp: Date.now(),
      });
    }
  }

  /**
   * Check if camera is currently running.
   */
  isActive() {
    return this.isRunning;
  }

  /**
   * Get current device ID.
   */
  getCurrentDeviceId() {
    return this.currentDeviceId;
  }

  /**
   * Clean up resources.
   */
  dispose() {
    this.stop();
    this.onFrame = null;
    this.onError = null;
    this.onDevicesChanged = null;
  }
}

