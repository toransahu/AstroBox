# coding=utf-8
__author__ = "Rafael Luque <rafael@astroprint.com>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import gi
import time
import logging
import os
import threading
import v4l2
import errno
import fcntl

from octoprint.events import eventManager, Events
from octoprint.settings import settings

gi.require_version('Gst', '1.0')
from gi.repository import Gst as gst

from astroprint.camera import CameraManager
from astroprint.webrtc import webRtcManager

from blinker import signal

gst.init(None)

class GStreamerManager(CameraManager):
	def __init__(self, number_of_video_device):
		self.number_of_video_device = number_of_video_device
		self.gstreamerVideo = None
		self.asyncPhotoTaker = None
		self._logger = logging.getLogger(__name__)
		self.supported_formats = None

		super(GStreamerManager, self).__init__()
		
	def open_camera(self):
		try:
			if self.gstreamerVideo is None:
				self.gstreamerVideo = GStreamer(self.number_of_video_device)

				self.supported_formats = self._get_supported_resolutions(self.number_of_video_device)

		except Exception, error:
			self._logger.error(error)
			self.gstreamerVideo = None

		return not self.gstreamerVideo is None

	def start_video_stream(self):
		if self.gstreamerVideo:
			if not self.isVideoStreaming():
				return self.gstreamerVideo.play_video()
			else:
				return True
		else:
			return False

	def stop_video_stream(self):
		if self.gstreamerVideo:
			return self.gstreamerVideo.stop_video()
		else:
			return False

	def settingsChanged(self, cameraSettings):
		##When a change in settup is saved, the camera must be shouted down
		##(Janus included, of course)
		self.stop_video_stream()
		webRtcManager().stopJanus()
		##

		if self.gstreamerVideo:
			self.gstreamerVideo.videotype = cameraSettings["encoding"]
			self.gstreamerVideo.size = cameraSettings["size"].split('x')
			self.gstreamerVideo.framerate = cameraSettings["framerate"]
			self.gstreamerVideo.format = cameraSettings["format"]

	# def list_camera_info(self):
	#    pass

	# def list_devices(self):
	#    pass

	# There are cases where we want the pic to be synchronous
	# so we leave this version too
	def get_pic(self, text=None):

		if self.gstreamerVideo:
			return self.gstreamerVideo.take_photo(text)

		return None

	def get_pic_async(self, done, text=None):
		# This is just a placeholder
		# we need to pass done around and call it with
		# the image info when ready
		if not self.gstreamerVideo:
			done(None)
			return

		if not self.asyncPhotoTaker:
			self.asyncPhotoTaker = AsyncPhotoTaker(self.gstreamerVideo.take_photo)

		self.asyncPhotoTaker.take_photo(done, text)
		
	# def save_pic(self, filename, text=None):
	#    pass

	def isCameraAvailable(self):

		parentCameraAvailable = super(GStreamerManager, self).isCameraAvailable()

		return self.gstreamerVideo is not None and parentCameraAvailable

	def isVideoStreaming(self):
		return self.gstreamerVideo.getStreamProcessState() == 'PLAYING'

	def getVideoStreamingState(self):
		return self.gstreamerVideo.streamProcessState

	def close_camera(self):
		if self.asyncPhotoTaker:
			self.asyncPhotoTaker.stop()

	def isResolutionSupported(self, resolution):

		resolutions = []

		for supported_format in self.supported_formats:
		    if supported_format.get('pixelformat') == 'YUYV':
		        resolutions = supported_format.get('resolutions')

		arrResolution = resolution.split('x')
		
		resolution = []
		
		for element in arrResolution:
			resolution += [long(element)]

		return resolution in resolutions

	def isCameraAble(self):

		return self.supported_formats is not None

	def _get_pixel_formats(self,device, maxformats=5):
	    """Query the camera to see what pixel formats it supports.  A list of
	    dicts is returned consisting of format and description.  The caller
	    should check whether this camera supports VIDEO_CAPTURE before
	    calling this function.
	    """
	    if '/dev/video' not in str(device):
	    	device = '/dev/video' + str(device)

	    supported_formats = []
	    fmt = v4l2.v4l2_fmtdesc()
	    fmt.index = 0
	    fmt.type = v4l2.V4L2_CAP_VIDEO_CAPTURE
	    try:
	        while fmt.index < maxformats:
	            with open(device, 'r') as vd:
	                if fcntl.ioctl(vd, v4l2.VIDIOC_ENUM_FMT, fmt) == 0:
	                    pixelformat = {}
	                    # save the int type for re-use later
	                    pixelformat['pixelformat_int'] = fmt.pixelformat
	                    pixelformat['pixelformat'] = "%s%s%s%s" % \
	                        (chr(fmt.pixelformat & 0xFF),
	                        chr((fmt.pixelformat >> 8) & 0xFF),
	                        chr((fmt.pixelformat >> 16) & 0xFF),
	                        chr((fmt.pixelformat >> 24) & 0xFF))
	                    pixelformat['description'] = fmt.description.decode()
	                    supported_formats.append(pixelformat)
	            fmt.index = fmt.index + 1
	    except IOError as e:
	        # EINVAL is the ioctl's way of telling us that there are no
	        # more formats, so we ignore it
	        if e.errno != errno.EINVAL:
	            print("Unable to determine Pixel Formats, this may be a "\
	                    "driver issue.")
	        return supported_formats
	    return supported_formats

	def _get_supported_resolutions(self, device):

		"""Query the camera for supported resolutions for a given pixel_format.
		Data is returned in a list of dictionaries with supported pixel
		formats as the following example shows:
		resolution['pixelformat'] = "YUYV"
		resolution['description'] = "(YUV 4:2:2 (YUYV))"
		resolution['resolutions'] = [[width, height], [640, 480], [1280, 720] ]

		If we are unable to gather any information from the driver, then we
		return YUYV and 640x480 which seems to be a safe default. Per the v4l2
		spec the ioctl used here is experimental but seems to be well supported.
		"""
		try:

			if '/dev/video' not in str(device):
				device = '/dev/video' + str(device)

			supported_formats = self._get_pixel_formats(device)

			if not supported_formats:
				resolution = {}
				resolution['description'] = "YUYV"
				resolution['pixelformat'] = "YUYV"
				resolution['resolutions'] = [[640, 480]]
				resolution['pixelformat_int'] = v4l2.v4l2_fmtdesc().pixelformat
				supported_formats.append(resolution)
				return supported_formats

			for supported_format in supported_formats:
			    resolutions = []
			    framesize = v4l2.v4l2_frmsizeenum()
			    framesize.index = 0
			    framesize.pixel_format = supported_format['pixelformat_int']
			    with open(device, 'r') as vd:
			        try:
			            while fcntl.ioctl(vd,v4l2.VIDIOC_ENUM_FRAMESIZES,framesize) == 0:
					if framesize.type == v4l2.V4L2_FRMSIZE_TYPE_DISCRETE:
			                    resolutions.append([framesize.discrete.width,
			                        framesize.discrete.height])
			                # for continuous and stepwise, let's just use min and
			                # max they use the same structure and only return
			                # one result
			                elif framesize.type == v4l2.V4L2_FRMSIZE_TYPE_CONTINUOUS or\
			                     framesize.type == v4l2.V4L2_FRMSIZE_TYPE_STEPWISE:
			                    resolutions.append([framesize.stepwise.min_width,
			                        framesize.stepwise.min_height])
			                    resolutions.append([framesize.stepwise.max_width,
			                        framesize.stepwise.max_height])
			                    break
			                framesize.index = framesize.index + 1
			        except IOError as e:
			            # EINVAL is the ioctl's way of telling us that there are no
			            # more formats, so we ignore it
			            if e.errno != errno.EINVAL:
			                print("Unable to determine supported framesizes "\
			                      "(resolutions), this may be a driver issue.")
			                return supported_formats
			    supported_format['resolutions'] = resolutions

			return supported_formats
		except Exception:
			self.cameraAble = False
			self._logger.info('Camera error: it is not posible to get the camera capabilities')
			#self.gstreamerVideo.fatalErrorManage('Camera error: it is not posible to get the camera capabilities. Please, try to reconnect the camera and try again...')

			self.supported_format = None
			return None

class GStreamer(object):
	
	# #THIS OBJECT COMPOSE A GSTREAMER LAUNCH LINE
	# IT ABLES FOR DEVELOPPERS TO MANAGE, WITH GSTREAMER,
	# THE PRINTER'S CAMERA: GET PHOTO AND VIDEO FROM IT
	def __init__(self, device):
		
		self._logger = logging.getLogger(__name__)

		try:
			self._logger.info("Initializing Gstreamer")

			self.videotype = settings().get(["camera", "encoding"])
			self.size = settings().get(["camera", "size"]).split('x')
			self.framerate = settings().get(["camera", "framerate"])
			self.format = settings().get(["camera", "format"])

			self.pipeline = None
			self.bus = None
			self.loop = None
			self.bus_managed = True
			self.takingPhotoCondition = threading.Condition()

			# VIDEO SOURCE DESCRIPTION
			# #DEVICE 0 (FIRST CAMERA) USING v4l2src DRIVER
			# #(v4l2src: VIDEO FOR LINUX TO SOURCE)
			self.video_source = gst.ElementFactory.make('v4l2src', 'video_source')
			self.video_source.set_property("device", '/dev/video' + str(device))
 
			# ASTROPRINT'S LOGO FROM DOWN RIGHT CORNER
			self.video_logo = gst.ElementFactory.make('gdkpixbufoverlay', 'logo_overlay')
			self.video_logo.set_property('location', '/AstroBox/src/astroprint/static/img/astroprint_logo.png')
			self.video_logo.set_property('overlay-width', 150)
			self.video_logo.set_property('overlay-height', 29)
			# ##
			# CONFIGURATION FOR TAKING PHOTOS
			# TEXT THAT APPEARS ON WHITE BAR WITH PERCENT PRINTING STATE INFO
			####
			self.photo_text = gst.ElementFactory.make('textoverlay', None)
			text = "<span foreground='#eb1716' background='white' font='nexa_boldregular' size='large'>0% - Layer - X / X </span>"
			self.photo_text.set_property('text', text)
			self.photo_text.set_property('valignment', 'top')
			self.photo_text.set_property('ypad', 0)
			self.photo_text.set_property('halignment', 'left')

			# ##
			# JPEG ENCODING COMMAND
			# ##
			self.jpegencNotText = gst.ElementFactory.make('jpegenc', 'jpegencNotText')
			self.jpegencNotText.set_property('quality',65)
			self.multifilesinkphotoNotText = None
			#####################

			# JPEG ENCODING COMMAND
			# ##
			self.jpegenc = gst.ElementFactory.make('jpegenc', 'jpegenc')
			self.jpegenc.set_property('quality',65)
			self.multifilesinkphoto = None
			#####################


			# ##
			# IMAGE FOR SAVING PHOTO
			self.tempImage = '/tmp/gstCapture.jpg'
			
			# STREAM DEFAULT STATE
			self.streamProcessState = 'PAUSED'
			
			self.photoMode = 'NOT_TEXT'

			self.reset_pipeline_gstreamer_state()
								
		except Exception, error:
			self._logger.error("Error initializing GStreamer's video pipeline: %s" % str(error))
			raise error


	def reset_pipeline_gstreamer_state(self):
		# SETS DEFAULT STATE FOR GSTREAMER OBJECT

		try:
			# ##
			# CAPS FOR GETTING IMAGES FROM VIDEO SOURCE
			self.video_logo.set_property('offset-x', int(self.size[0]) - 160)
			self.video_logo.set_property('offset-y', int(self.size[1]) - 30)
						
			if self.format == 'x-h264' and self.videotype == 'h264':
			
				camera1caps = gst.Caps.from_string('video/x-h264,width=' + self.size[0] + ',height=' + self.size[1] + ',framerate=' + self.framerate + '/1')

				self.x264parse = gst.ElementFactory.make('h264parse',None)
				self.x264dec = gst.ElementFactory.make('omxh264dec',None)

				self.x264parseNotText = gst.ElementFactory.make('h264parse',None)
				self.x264decNotText = gst.ElementFactory.make('omxh264dec',None)

			else:

				camera1caps = gst.Caps.from_string('video/x-raw,format=I420,width=' + self.size[0] + ',height=' + self.size[1] + ',framerate=' + self.framerate + '/1')


			self.src_caps = gst.ElementFactory.make("capsfilter", "filter1")
			self.src_caps.set_property("caps", camera1caps)
			# ##

			# ##
			# CONFIGURATION FOR TAKING PHOTOS
			####
			# LOGO AND WHITE BAR FROM TOP LEFT CORNER THAT APPEARS 
			# IN THE VIDEO COMPOSED BY PHOTOS TAKEN WHILE PRINTING    
			####
			self.photo_logo = gst.ElementFactory.make('gdkpixbufoverlay', None)
			self.photo_logo.set_property('location', '/AstroBox/src/astroprint/static/img/camera-info-overlay.jpg')
			self.photo_logo.set_property('offset-x', 0)
			self.photo_logo.set_property('offset-y', 0)
			if self.size[1] == '720':
				self.photo_logo.set_property('overlay-width',449)
				self.photo_logo.set_property('overlay-height',44)
				self.photo_text.set_property('xpad', 70)
			else:
				self.photo_text.set_property('xpad', 35)
			####
			# ##
			# ##
			# TEE COMMAND IN GSTREAMER ABLES TO JOIN NEW OUTPUT
			# QUEUES TO THE SAME SOURCE 
			self.tee = gst.ElementFactory.make('tee', 'tee')
			# ##
			
			# ##
			# PIPELINE IS THE MAIN PIPE OF GSTREAMER FOR GET IMAGES
			# FROM A SOURCE
			# ##
			self.pipeline = gst.Pipeline()
			self.bus = self.pipeline.get_bus()
			self.pipeline.set_property('name', 'tee-pipeline')
			# self.bus.add_signal_watch_full(1)
			self.bus.add_signal_watch()
			self.bus.connect('message', self.bus_message)			
			# SOURCE, CONVERSIONS AND OUTPUTS (QUEUES) HAVE TO BE
			# ADDED TO PIPELINE
			self.pipeline.add(self.video_source)
			self.pipeline.add(self.video_logo)
			self.pipeline.add(self.src_caps)
			self.pipeline.add(self.tee)
			# ##
		   
			# ##
			# LINKS MAKE A GSTREAMER LINE, LIKE AN IMAGINE TRAIN
			# WICH WAGONS ARE LINKED IN LINE OR QUEUE
			# ##
			if self.format == 'x-raw':
				self.video_source.link(self.video_logo)
				self.video_logo.link(self.src_caps)
				self.src_caps.link(self.tee)
			else:#x-h264
				self.video_source.link(self.src_caps)
				self.src_caps.link(self.tee)
			# ##
			
			# ##
			# OBJECTS FOR GETTING IMAGES FROM VIDEO SOURCE IN BINARY,
			# USED FOR GET PHOTOS
			# ##
			self.queuebin = None
			self.tee_video_pad_bin = None        
			self.queue_videobin_pad = None
			self.queuebinNotText = None
			self.tee_video_pad_binNotText = None        
			self.queue_videobin_padNotText = None
			# ##
			
			self.streamProcessState = 'PAUSED'

			self.photoMode = 'NOT_TEXT'

			return True
		
		except Exception, error:
			self._logger.error("Error resetting GStreamer's video pipeline: %s" % str(error))
			if self.pipeline:
				self.pipeline.set_state(gst.State.PAUSED)
				self.pipeline.set_state(gst.State.NULL)
			
			return False
		
	def play_video(self):

		if not self.streamProcessState == 'PREPARING_VIDEO' or not  self.streamProcessState == 'PLAYING':
			# SETS VIDEO ENCODING PARAMETERS AND STARTS VIDEO
			try:
				waitingForVideo = True

				self.waitForPlayVideo = threading.Event()
			
				while waitingForVideo:
					if self.streamProcessState == 'TAKING_PHOTO' or self.streamProcessState == '':
						waitingForVideo = self.waitForPlayVideo.wait(2)
					else:
						self.waitForPlayVideo.set()
						self.waitForPlayVideo.clear()
						waitingForVideo = False

				self.streamProcessState = 'PREPARING_VIDEO'

				# ##
				# CAPS FOR GETTING IMAGES FROM VIDEO SOURCE
				self.video_logo.set_property('offset-x', int(self.size[0]) - 160)
				self.video_logo.set_property('offset-y', int(self.size[1]) - 30)
				# ##
				
				# ##
				# GSTRAMER MAIN QUEUE: DIRECTLY CONNECTED TO SOURCE
				queueraw = gst.ElementFactory.make('queue', 'queueraw')
				# ##
				
				# ##
				# MODE FOR BROADCASTING VIDEO
				udpsinkout = gst.ElementFactory.make('udpsink', 'udpsinkvideo')
				udpsinkout.set_property('host', '127.0.0.1')
				# ##

				encode = None
				h264parse = None
		
				if self.videotype == 'h264':
					# ##
					# H264 VIDEO MODE SETUP
					# ##
					# ENCODING
					if self.format == 'x-raw':
						encode = gst.ElementFactory.make('omxh264enc', None)
						# CAPABILITIES FOR H264 OUTPUT
						camera1capsout = gst.Caps.from_string('video/x-h264,profile=high')
						enc_caps = gst.ElementFactory.make("capsfilter", "filter2")
						enc_caps.set_property("caps", camera1capsout)
					else:
						h264parse = gst.ElementFactory.make('h264parse',None)


					# VIDEO PAY FOR H264 BEING SHARED IN UDP PACKAGES
					videortppay = gst.ElementFactory.make('rtph264pay', 'rtph264pay')
					videortppay.set_property('pt', 96)
					# UDP PORT FOR SHARING H264 VIDEO
					udpsinkout.set_property('port', 8004)
					# ##
					
				elif self.videotype == 'vp8':
					# ##
					# VP8 VIDEO MODE STUP
					# ##
					# ENCODING
					encode = gst.ElementFactory.make('vp8enc', None)
					encode.set_property('target-bitrate', 500000)
					encode.set_property('keyframe-max-dist', 500)
					#####VERY IMPORTANT FOR VP8 ENCODING: NEVER USES deadline = 0 (default value)
					encode.set_property('deadline', 1)
					#####
					# VIDEO PAY FOR VP8 BEING SHARED IN UDP PACKAGES                
					videortppay = gst.ElementFactory.make('rtpvp8pay', 'rtpvp8pay')
					videortppay.set_property('pt', 96)
					# UDP PORT FOR SHARING VP8 VIDEO
					udpsinkout.set_property('port', 8005)
					# ##
				
				# ##
				# ADDING VIDEO ELEMENTS TO PIPELINE
				self.pipeline.add(queueraw)
				if not (self.format == 'x-h264' and self.videotype == 'h264'):
					self.pipeline.add(encode)
				else:
					self.pipeline.add(h264parse)
				
				if self.videotype == 'h264' and self.format == 'x-raw':
						self.pipeline.add(enc_caps)

				self.pipeline.add(videortppay)
				self.pipeline.add(udpsinkout)
				
				if self.videotype == 'h264':

					if self.format == 'x-raw':

						queueraw.link(encode)
						encode.link(enc_caps)
						enc_caps.link(videortppay)
					else:#x-h264

						queueraw.link(h264parse)
						h264parse.link(videortppay)

				else:#VP8
					queueraw.link(encode)
					encode.link(videortppay)

					
				videortppay.link(udpsinkout)

				# CONFIGURATION FOR TAKING SOME FILES (PHOTO) FOR GETTING
				# A GOOD IMAGE FROM CAMERA
				self.multifilesinkphoto = gst.ElementFactory.make('multifilesink', 'multifilesink')
				self.multifilesinkphoto.set_property('location', self.tempImage)
				self.multifilesinkphoto.set_property('max-files', 1)
				self.multifilesinkphoto.set_property('post-messages', True)
				self.multifilesinkphoto.set_property('async', True)
				self.multifilesinkphotoNotText = gst.ElementFactory.make('multifilesink', 'multifilesinkNotText')
				self.multifilesinkphotoNotText.set_property('location', self.tempImage)
				self.multifilesinkphotoNotText.set_property('max-files', 1)
				self.multifilesinkphotoNotText.set_property('post-messages', True)
				self.multifilesinkphotoNotText.set_property('async', True)

				# QUEUE FOR TAKING PHOTOS    
				self.queuebin = gst.ElementFactory.make('queue', 'queuebin')
				# ##
				# QUEUE FOR TAKING PHOTOS (without text)
				self.queuebinNotText = gst.ElementFactory.make('queue', 'queuebinNotText')
				# ##

				# ADDING PHOTO QUEUE TO PIPELINE
				self.pipeline.add(self.queuebin)

				if self.format == 'x-h264' and self.videotype == 'h264':
					self.pipeline.add(self.x264dec)
					self.pipeline.add(self.x264parse)
				
				self.pipeline.add(self.photo_logo)
				self.pipeline.add(self.photo_text)
				self.pipeline.add(self.jpegenc)
				# ADDING PHOTO QUEUE (without text) TO PIPELINE
				self.pipeline.add(self.queuebinNotText)
				
				if self.format == 'x-h264' and self.videotype == 'h264':
					self.pipeline.add(self.x264decNotText)
					self.pipeline.add(self.x264parseNotText)

				self.pipeline.add(self.jpegencNotText)
				# #

				# PREPARING PHOTO
				# SETTING THE TEXT INFORMATION ABOUT THE PRINTING STATE IN PHOTO
				text = "<span foreground='#eb1716' background='white' font='nexa_boldregular' size='large'></span>"
				self.photo_text.set_property('text', text)
				# LINKING PHOTO ELEMENTS (INCLUDED TEXT)
				
				if self.format == 'x-h264' and self.videotype == 'h264':
					self.queuebin.link(self.x264parse)
					self.x264parse.link(self.x264dec)
					self.x264dec.link(self.photo_logo)
					self.photo_logo.link(self.photo_text)
					self.photo_text.link(self.jpegenc)
				else:
					self.queuebin.link(self.photo_logo)
					self.photo_logo.link(self.photo_text)
					self.photo_text.link(self.jpegenc)

				# LINKING PHOTO ELEMENTS (WITHOUT TEXT ON PHOTO)
				if self.format == 'x-h264' and self.videotype == 'h264':
					self.queuebinNotText.link(self.x264parseNotText)
					self.x264parseNotText.link(self.x264decNotText)
					self.x264decNotText.link(self.jpegencNotText)
				else:
					self.queuebinNotText.link(self.jpegencNotText)
				##########
				
				# TEE PADDING MANAGING
				# #TEE SOURCE H264
				tee_video_pad_video = self.tee.get_request_pad("src_%u")
				
				# TEE SINKING MANAGING
				# #VIDEO SINK QUEUE
				queue_video_pad = queueraw.get_static_pad("sink")
		
				# TEE PAD LINK
				# #VIDEO PADDING        
				gst.Pad.link(tee_video_pad_video, queue_video_pad)
				  
				# START PLAYING THE PIPELINE
				self.streamProcessState = 'PLAYING'
				self.pipeline.set_state(gst.State.PLAYING)
				
				self.pipeline.add(self.multifilesinkphotoNotText)

				self.pipeline.add(self.multifilesinkphoto)

				return True
				
			except Exception, error:
				self._logger.error("Error playing video with GStreamer: %s" % str(error))
				self.pipeline.set_state(gst.State.PAUSED)
				self.pipeline.set_state(gst.State.NULL)
				self.reset_pipeline_gstreamer_state()
				
				return False

	def stop_video(self):
		# STOPS THE VIDEO
		try:
			if self.streamProcessState == 'TAKING_PHOTO':
				self.queueraw.set_state(gst.State.PAUSED)

			waitingForStopPipeline = True

			self.waitForPlayPipeline = threading.Event()
		
			while waitingForStopPipeline:
				if self.streamProcessState == 'TAKING_PHOTO' or self.streamProcessState == '':
					waitingForStopPipeline = self.waitForPlayPipeline.wait(2)
				else:
					self.waitForPlayPipeline.set()
					self.waitForPlayPipeline.clear()
					waitingForStopPipeline = False

			self.pipeline.set_state(gst.State.NULL)
			self.reset_pipeline_gstreamer_state()
			self.streamProcessState = 'PAUSED'

			return True
				
		except Exception, error:
			
			self._logger.error("Error stopping video with GStreamer: %s" % str(error))
			self.pipeline.set_state(gst.State.PAUSED)
			self.pipeline.set_state(gst.State.NULL)
			self.reset_pipeline_gstreamer_state()
			
			return False

	def bus_message(self, bus, msg):
		
		t = msg.type

		if t == gst.MessageType.ELEMENT:

			if 'GstMultiFileSink' in msg.src.__class__.__name__:

				if not self.bus_managed:

					self.bus_managed = True

					if self.photoMode == 'NOT_TEXT':
						try:
							self.tee_video_pad_binNotText.add_probe(gst.PadProbeType.BLOCK_DOWNSTREAM, self.video_bin_pad_probe_callback, None)
						except Exception, error:
							self._logger.error("ERROR IN BUS MESSAGE: %s", error)
							self.fatalErrorManage(True, True)
						
					else:
						try:
							self.tee_video_pad_bin.add_probe(gst.PadProbeType.BLOCK_DOWNSTREAM, self.video_bin_pad_probe_callback, None)
	
						except Exception, error:
							self._logger.error("ERROR IN BUS MESSAGE: %s", error)
							self.fatalErrorManage(True, True)

		elif t == gst.MessageType.ERROR:
			
			busError, detail = msg.parse_error()

			print busError
			print detail

			self._logger.error("gstreamer bus message error: %s" % busError)

			if 'Internal data flow error.' in str(busError):
				self.fatalErrorManage(True,True,str(busError)+' Did you selected a correct "Video Format" and resolution in settings? Please, change the camera resolution and/or video format, and try it again')

	def video_bin_pad_probe_callback(self, pad, info, user_data):

		if info.id == 1:
	
			if self.photoMode == 'NOT_TEXT':
				
				try:
					self.tee_video_pad_binNotText.remove_probe(info.id)
					self.queuebinNotText.set_state(gst.State.PAUSED)
					
					if self.streamProcessState == 'TAKING_PHOTO':
						self.queuebinNotText.set_state(gst.State.NULL)

					self.jpegencNotText.unlink(self.multifilesinkphotoNotText)
				
				except:
				
					self._logger.error("ERROR IN VIDEO_BIN_PAD_PROBE_CALLBACK: %s", error)
					
					if self.streamProcessState == 'TAKING_PHOTO':
						self.queuebinNotText.set_state(gst.State.PAUSED)
						self.queuebinNotText.set_state(gst.State.NULL)
					
					self.waitForPhoto.set()
					self.fatalErrorManage(True, True)
				
					return gst.PadProbeReturn.DROP

			else:

				try:
					
					self.tee_video_pad_bin.remove_probe(info.id)
					self.queuebin.set_state(gst.State.PAUSED)
					
					if self.streamProcessState == 'TAKING_PHOTO':
						self.queuebin.set_state(gst.State.NULL)

					self.jpegenc.unlink(self.multifilesinkphoto)

				except Exception, error:
					
					self._logger.error("ERROR IN VIDEO_BIN_PAD_PROBE_CALLBACK: %s", error)

					if self.streamProcessState == 'TAKING_PHOTO':
						self.queuebin.set_state(gst.State.PAUSED)
						self.queuebin.set_state(gst.State.NULL)

					self.waitForPhoto.set()
					self.fatalErrorManage(True, True)
					
					return gst.PadProbeReturn.DROP

			self.waitForPhoto.set()

			return gst.PadProbeReturn.OK

		else:

			return gst.PadProbeReturn.DROP

	def take_photo(self, textPhoto, tryingTimes=0):
		with self.takingPhotoCondition:

			self.waitForPhoto = threading.Event()
			
			if self.streamProcessState == 'PREPARING_VIDEO' or self.streamProcessState == '':
				
				waitingState = self.waitForPhoto.wait(5)
				self.waitForPhoto.clear()
				
				# waitingState values:
				#  - True: exit before timeout. The device is able to take photo because video was stablished.
				#  - False: timeout given. The device is busy stablishing video. It is not able to take photo yet.

				if not waitingState:
					return None


			# threading.wait(5000)
			# self.sem = threading.Semaphore(0)

			# TAKES A PHOTO USING GSTREAMER
			self.take_photo_and_return(textPhoto)
			# THEN, WHEN PHOTO IS STORED, THIS IS REMOVED PHISICALLY
			# FROM HARD DISK FOR GETTING NEW PHOTOS AND FREEING SPACE

			photo = None

			try:
				if self.format == 'x-h264' and self.videotype == 'h264':
					time = 10;
				else:
					time = 7

				waitingState = self.waitForPhoto.wait(tryingTimes*3+time)
				# waitingState values:
				#  - True: exit before timeout
				#  - False: timeout given

				if self.streamProcessState == 'TAKING_PHOTO':

					self.pipeline.set_state(gst.State.PAUSED)
					self.pipeline.set_state(gst.State.NULL)

					self.reset_pipeline_gstreamer_state()


				if waitingState:

					try:
						
						with open(self.tempImage, 'r') as fin:
							photo = fin.read()
						
						os.unlink(self.tempImage)
						
					except:
						self._logger.error('Error while opening photo file: recomposing photo maker process...')

				else:
					
					if tryingTimes >= 3:
							
							if self.streamProcessState != 'PAUSED':#coming from fatal error from bus...
							
								stateBeforeError = self.streamProcessState
								self.stop_video()
								self.reset_pipeline_gstreamer_state()
							
								if stateBeforeError == 'PLAYING':
									self.play_video()

							return None

					if not self.bus_managed:

						self._logger.error('Error in Gstreamer: bus does not get a GstMultiFileSink kind of message. Resetting pipeline...')

						if self.streamProcessState == 'PLAYING':
						
							self.stop_video()
							self.reset_pipeline_gstreamer_state()
							self.play_video()

						self.bus_managed = True

						if tryingTimes == 2:
							self._logger.error('Error in Gstreamer: Fatal error: photo queue is not able to be turned on. Gstreamer\'s bus does not get a GstMultiFileSink kind of message')

						return self.take_photo(textPhoto,tryingTimes+1)

					else:

						return self.take_photo(textPhoto,tryingTimes+1)

			except Exception, error:
				
				self.waitForPhoto.clear()
				
				if self.streamProcessState == 'TAKING_PHOTO':

					self.pipeline.set_state(gst.State.PAUSED)
					self.pipeline.set_state(gst.State.NULL)

					self.reset_pipeline_gstreamer_state()

				self._logger.error("take_photo except:  %s" % str(error))
				self.waitForPhoto.clear()
	
				return None

			return photo

	def take_photo_and_return(self, textPhoto):
		
		# TAKES A PHOTO USING GSTREAMER
		try:	
			
			try:
				if self.streamProcessState == 'PAUSED':
	
					# SETTING THE TEXT INFORMATION ABOUT THE PRINTING STATE IN PHOTO
					if textPhoto is None:
						# CONFIGURATION FOR TAKING SOME FILES (PHOTO) FOR GETTING
						# A GOOD IMAGE FROM CAMERA
						self.multifilesinkphotoNotText = gst.ElementFactory.make('multifilesink', 'multifilesikNotText')
						self.multifilesinkphotoNotText.set_property('location', self.tempImage)
						self.multifilesinkphotoNotText.set_property('max-files', 1)
						self.multifilesinkphotoNotText.set_property('post-messages', True)
						self.multifilesinkphotoNotText.set_property('async', True)			

						# QUEUE FOR TAKING PHOTOS    
						self.queuebinNotText = gst.ElementFactory.make('queue', 'queuebinNotText')
						# ##

						# ADDING PHOTO QUEUE TO PIPELINE
						self.pipeline.add(self.queuebinNotText)
						if self.format == 'x-h264' and self.videotype == 'h264':
							self.pipeline.add(self.x264decNotText)
							self.pipeline.add(self.x264parseNotText)

						self.pipeline.add(self.jpegencNotText)						
						##
						
						# LINKING PHOTO ELEMENTS (WITHOUT TEXT ON PHOTO)
						if self.format == 'x-h264' and self.videotype == 'h264':
							self.queuebinNotText.link(self.x264parseNotText)
							self.x264parseNotText.link(self.x264decNotText)
							self.x264decNotText.link(self.video_logo)
							self.video_logo.link(self.jpegencNotText)
						else:
							self.queuebinNotText.link(self.jpegencNotText)
						##########
					
						self.pipeline.add(self.multifilesinkphotoNotText)

					else:

						# CONFIGURATION FOR TAKING SOME FILES (PHOTO) FOR GETTING
						# A GOOD IMAGE FROM CAMERA
						self.multifilesinkphoto = gst.ElementFactory.make('multifilesink', 'multifilesink')
						self.multifilesinkphoto.set_property('location', self.tempImage)
						self.multifilesinkphoto.set_property('max-files', 1)
						self.multifilesinkphoto.set_property('post-messages', True)
						self.multifilesinkphoto.set_property('async', True)		


						# QUEUE FOR TAKING PHOTOS    
						self.queuebin = gst.ElementFactory.make('queue', 'queuebin')
						# ##

						# ADDING PHOTO QUEUE TO PIPELINE
						self.pipeline.add(self.queuebin)
						if self.format == 'x-h264' and self.videotype == 'h264':
							self.pipeline.add(self.x264dec)
							self.pipeline.add(self.x264parse)

						self.pipeline.add(self.photo_logo)
						self.pipeline.add(self.photo_text)
						self.pipeline.add(self.jpegenc)
						##
				
						# LINKING PHOTO ELEMENTS (INCLUDED TEXT)
						if self.format == 'x-h264' and self.videotype == 'h264':
							self.queuebin.link(self.x264parse)
							self.x264parse.link(self.x264dec)
							self.x264dec.link(self.video_logo)
							self.video_logo.link(self.photo_logo)
							self.photo_logo.link(self.photo_text)
							self.photo_text.link(self.jpegenc)
						else:
							self.queuebin.link(self.photo_logo)
							self.photo_logo.link(self.photo_text)
							self.photo_text.link(self.jpegenc)
		
						self.pipeline.add(self.multifilesinkphoto)

					self.streamProcessState = 'TAKING_PHOTO'
				
					self.pipeline.set_state(gst.State.PLAYING)

			except Exception, error:
				
				self._logger.error("Error taking photo with GStreamer: %s" % str(error))
				self.pipeline.set_state(gst.State.PAUSED)
				self.pipeline.set_state(gst.State.NULL)
				self.reset_pipeline_gstreamer_state()

				return None				


			###############

			if textPhoto is None:
				try:
					self.photoMode = 'NOT_TEXT'

					self.jpegencNotText.link(self.multifilesinkphotoNotText)

					self.tee_video_pad_binNotText = self.tee.get_request_pad("src_%u")
					self.queue_videobin_padNotText = self.queuebinNotText.get_static_pad("sink")	

					gst.Pad.link(self.tee_video_pad_binNotText, self.queue_videobin_padNotText)

					self.queuebinNotText.set_state(gst.State.PLAYING)

				except Exception, error:
					
					self._logger.error("Error taking photo with GStreamer: %s" % str(error))
					self.pipeline.set_state(gst.State.PAUSED)
					self.pipeline.set_state(gst.State.NULL)
					self.reset_pipeline_gstreamer_state()
				
			else:

				try:

					# SETTING THE TEXT INFORMATION ABOUT THE PRINTING STATE IN PHOTO
					text = "<span foreground='#eb1716' background='white' font='nexa_boldregular' size='large'>  " + textPhoto + "  </span>"
					self.photo_text.set_property('text', text)

					self.photoMode = 'TEXT'

					self.jpegenc.link(self.multifilesinkphoto)

					self.tee_video_pad_bin = self.tee.get_request_pad("src_%u")
					self.queue_videobin_pad = self.queuebin.get_static_pad("sink")

					gst.Pad.link(self.tee_video_pad_bin, self.queue_videobin_pad)

					self.queuebin.set_state(gst.State.PLAYING)

				except Exception, error:
					
					self._logger.error("Error taking photo with GStreamer: %s" % str(error))
					self.pipeline.set_state(gst.State.PAUSED)
					self.pipeline.set_state(gst.State.NULL)
					self.reset_pipeline_gstreamer_state()

			self.bus_managed = False

			return None

		except Exception, error:
			
			self._logger.error("Error taking photo with GStreamer: %s" % str(error))
			self.pipeline.set_state(gst.State.PAUSED)
			self.pipeline.set_state(gst.State.NULL)
			self.reset_pipeline_gstreamer_state()
			
			return None

		
	def getStreamProcessState(self):
		# RETURNS THE CURRENT STREAM STATE
		return self.streamProcessState

	def fatalErrorManage(self, NULLToQueuebinNotText=True, NULLToQueuebin=True, Message=None):

		self._logger.error('Gstreamer fatal error managing')
		
		if NULLToQueuebinNotText and self.queuebinNotText:
				self.queuebinNotText.set_state(gst.State.PAUSED)
				self.queuebinNotText.set_state(gst.State.NULL)
		
		if NULLToQueuebin and self.queuebin:
			self.queuebin.set_state(gst.State.PAUSED)
			self.queuebin.set_state(gst.State.NULL)
		
		self.pipeline.set_state(gst.State.PAUSED)
		self.pipeline.set_state(gst.State.NULL)
		self.reset_pipeline_gstreamer_state()

		#signaling for remote peers
		ready = signal('manage_fatal_error')
		ready.send('cameraError',message=Message)

		#event for local peers
		eventManager().fire(Events.GSTREAMER_EVENT, {
			'message': Message or 'Fatal error occurred in video streaming'
		})


class AsyncPhotoTaker(threading.Thread):
	def __init__(self, take_photo_function):
		
		super(AsyncPhotoTaker, self).__init__()
		
		self.threadAlive = True

		self.take_photo_function = take_photo_function

		self.sem = threading.Semaphore(0)
		self.doneFunc = None
		self.text = None
		self.start()

	def run(self):
		while self.threadAlive:
			self.sem.acquire()
			if not self.threadAlive:
				return

			if self.doneFunc:
				self.doneFunc(self.take_photo_function(self.text))
				self.doneFunc = None
				self.text = None

	def take_photo(self, done, text):
		self.doneFunc = done
		self.text = text
		self.sem.release()

	def stop(self):
		self.threadAlive = False
		self.sem.release()

