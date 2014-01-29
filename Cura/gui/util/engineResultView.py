__copyright__ = "Copyright (C) 2013 David Braam - Released under terms of the AGPLv3 License"

import wx
import numpy
import math

import OpenGL
#OpenGL.ERROR_CHECKING = False
from OpenGL.GLU import *
from OpenGL.GL import *

from Cura.util import profile
from Cura.gui.util import opengl
from Cura.gui.util import openglGui

class engineResultView(object):
	def __init__(self, parent):
		self._parent = parent
		self._result = None
		self._enabled = False
		self._layerVBOs = []
		self._layer20VBOs = []

		self.layerSelect = openglGui.glSlider(self._parent, 10000, 0, 1, (-1,-2), lambda : self._parent.QueueRefresh())

	def setResult(self, result):
		if self._result == result:
			return

		self._result = result

		#Clean the saved VBO's
		for layer in self._layerVBOs:
			for typeName in layer.keys():
				self._parent.glReleaseList.append(layer[typeName])
		for layer in self._layer20VBOs:
			for typeName in layer.keys():
				self._parent.glReleaseList.append(layer[typeName])
		self._layerVBOs = []
		self._layer20VBOs = []

	def setEnabled(self, enabled):
		self._enabled = enabled
		self.layerSelect.setHidden(not enabled)

	def OnDraw(self):
		if not self._enabled:
			return

		result = self._result
		if result is not None and result._polygons is not None:
			self.layerSelect.setRange(1, len(result._polygons))

		glPushMatrix()
		glEnable(GL_BLEND)
		if profile.getMachineSetting('machine_center_is_zero') != 'True':
			glTranslate(-profile.getMachineSettingFloat('machine_width') / 2, -profile.getMachineSettingFloat('machine_depth') / 2, 0)
		glLineWidth(2)

		layerNr = self.layerSelect.getValue()
		if layerNr == self.layerSelect.getMaxValue():
			layerNr = max(layerNr, len(result._polygons))
		viewZ = (layerNr - 1) * profile.getProfileSettingFloat('layer_height') + profile.getProfileSettingFloat('bottom_thickness')
		self._parent._viewTarget[2] = viewZ
		msize = max(profile.getMachineSettingFloat('machine_width'), profile.getMachineSettingFloat('machine_depth'))
		lineTypeList = [
			('inset0',     'WALL-OUTER', [1,0,0,1]),
			('insetx',     'WALL-INNER', [0,1,0,1]),
			('openoutline', None,        [1,0,0,1]),
			('skin',       'FILL',       [1,1,0,1]),
			('infill',      None,        [1,1,0,1]),
			('support',    'SUPPORT',    [0,1,1,1]),
			('skirt',      'SKIRT',      [0,1,1,1]),
			('outline',     None,        [0,0,0,1])
		]
		n = layerNr - 1
		gcodeLayers = result.getGCodeLayers()
		generatedVBO = False
		while n >= 0:
			if layerNr - n > 30 and n % 20 == 0:
				idx = n / 20
				while len(self._layer20VBOs) < idx + 1:
					self._layer20VBOs.append({})
				if result is not None and result._polygons is not None and n + 20 < len(result._polygons):
					layerVBOs = self._layer20VBOs[idx]
					for typeName, _, color in lineTypeList:
						if typeName in result._polygons[n + 19]:
							if typeName not in layerVBOs:
								if generatedVBO:
									continue
								polygons = []
								for i in xrange(0, 20):
									if typeName in result._polygons[n + i]:
										polygons += result._polygons[n + i][typeName]
								layerVBOs[typeName] = self._polygonsToVBO_lines(polygons)
								generatedVBO = True
							glColor4f(color[0]*0.5,color[1]*0.5,color[2]*0.5,color[3])
							layerVBOs[typeName].render()
				n -= 20
			else:
				c = 1.0 - ((layerNr - n) - 1) * 0.05
				c = max(0.5, c)
				while len(self._layerVBOs) < n + 1:
					self._layerVBOs.append({})
				layerVBOs = self._layerVBOs[n]
				if gcodeLayers is not None and layerNr - 10 < n < (len(gcodeLayers) - 1):
					for _, typeName, color in lineTypeList:
						if typeName is None:
							continue
						if 'GCODE-' + typeName not in layerVBOs:
							layerVBOs['GCODE-' + typeName] = self._gcodeToVBO_quads(gcodeLayers[n+1:n+2], typeName)
						glColor4f(color[0]*c,color[1]*c,color[2]*c,color[3])
						layerVBOs['GCODE-' + typeName].render()

					if n == layerNr - 1:
						if 'GCODE-MOVE' not in layerVBOs:
							layerVBOs['GCODE-MOVE'] = self._gcodeToVBO_lines(gcodeLayers[n+1:n+2])
						glColor4f(0,0,c,1)
						layerVBOs['GCODE-MOVE'].render()
				elif result is not None and result._polygons is not None and n < len(result._polygons):
					polygons = result._polygons[n]
					for typeName, _, color in lineTypeList:
						if typeName in polygons:
							if typeName not in layerVBOs:
								layerVBOs[typeName] = self._polygonsToVBO_lines(polygons[typeName])
							glColor4f(color[0]*c,color[1]*c,color[2]*c,color[3])
							layerVBOs[typeName].render()
				n -= 1
		glPopMatrix()
		if generatedVBO:
			self._parent._queueRefresh()

	def _polygonsToVBO_lines(self, polygons):
		verts = numpy.zeros((0, 3), numpy.float32)
		indices = numpy.zeros((0), numpy.uint32)
		for poly in polygons:
			if len(poly) > 2:
				i = numpy.arange(len(verts), len(verts) + len(poly) + 1, 1, numpy.uint32)
				i[-1] = len(verts)
				i = numpy.dstack((i[0:-1],i[1:])).flatten()
			else:
				i = numpy.arange(len(verts), len(verts) + len(poly), 1, numpy.uint32)
			indices = numpy.concatenate((indices, i), 0)
			verts = numpy.concatenate((verts, poly), 0)
		return opengl.GLVBO(GL_LINES, verts, indicesArray=indices)

	def _polygonsToVBO_quads(self, polygons):
		verts = numpy.zeros((0, 3), numpy.float32)
		indices = numpy.zeros((0), numpy.uint32)
		for poly in polygons:
			i = numpy.arange(len(verts), len(verts) + len(poly) + 1, 1, numpy.uint32)
			i2 = numpy.arange(len(verts) + len(poly), len(verts) + len(poly) + len(poly) + 1, 1, numpy.uint32)
			i[-1] = len(verts)
			i2[-1] = len(verts) + len(poly)
			i = numpy.dstack((i[0:-1],i2[0:-1],i2[1:],i[1:])).flatten()
			indices = numpy.concatenate((indices, i), 0)
			verts = numpy.concatenate((verts, poly), 0)
			verts = numpy.concatenate((verts, poly * numpy.array([1,0,1],numpy.float32) + numpy.array([0,-100,0],numpy.float32)), 0)
		return opengl.GLVBO(GL_QUADS, verts, indicesArray=indices)

	def _gcodeToVBO_lines(self, gcodeLayers, extrudeType):
		if ':' in extrudeType:
			extruder = int(extrudeType[extrudeType.find(':')+1:])
			extrudeType = extrudeType[0:extrudeType.find(':')]
		else:
			extruder = None
		verts = numpy.zeros((0, 3), numpy.float32)
		indices = numpy.zeros((0), numpy.uint32)
		for layer in gcodeLayers:
			for path in layer:
				if path['type'] == 'extrude' and path['pathType'] == extrudeType and (extruder is None or path['extruder'] == extruder):
					i = numpy.arange(len(verts), len(verts) + len(path['points']), 1, numpy.uint32)
					i = numpy.dstack((i[0:-1],i[1:])).flatten()
					indices = numpy.concatenate((indices, i), 0)
					verts = numpy.concatenate((verts, path['points']))
		return opengl.GLVBO(GL_LINES, verts, indicesArray=indices)

	def _gcodeToVBO_quads(self, gcodeLayers, extrudeType):
		useFilamentArea = profile.getMachineSetting('gcode_flavor') == 'UltiGCode'
		filamentRadius = profile.getProfileSettingFloat('filament_diameter') / 2
		filamentArea = math.pi * filamentRadius * filamentRadius

		if ':' in extrudeType:
			extruder = int(extrudeType[extrudeType.find(':')+1:])
			extrudeType = extrudeType[0:extrudeType.find(':')]
		else:
			extruder = None

		verts = numpy.zeros((0, 3), numpy.float32)
		indices = numpy.zeros((0), numpy.uint32)
		for layer in gcodeLayers:
			for path in layer:
				if path['type'] == 'extrude' and path['pathType'] == extrudeType and (extruder is None or path['extruder'] == extruder):
					a = path['points']
					if extrudeType == 'FILL':
						a[:,2] += 0.01

					#Construct the normals of each line 90deg rotated on the X/Y plane
					normals = a[1:] - a[:-1]
					lengths = numpy.sqrt(normals[:,0]**2 + normals[:,1]**2)
					normals[:,0], normals[:,1] = -normals[:,1] / lengths, normals[:,0] / lengths
					normals[:,2] /= lengths

					ePerDist = path['extrusion'][1:] / lengths
					if useFilamentArea:
						lineWidth = ePerDist / path['layerThickness'] / 2.0
					else:
						lineWidth = ePerDist * (filamentArea / path['layerThickness'] / 2)

					normals[:,0] *= lineWidth
					normals[:,1] *= lineWidth

					b = numpy.zeros((len(a)-1, 0), numpy.float32)
					b = numpy.concatenate((b, a[1:] + normals), 1)
					b = numpy.concatenate((b, a[1:] - normals), 1)
					b = numpy.concatenate((b, a[:-1] - normals), 1)
					b = numpy.concatenate((b, a[:-1] + normals), 1)
					b = b.reshape((len(b) * 4, 3))

					i = numpy.arange(len(verts), len(verts) + len(b), 1, numpy.uint32)

					verts = numpy.concatenate((verts, b))
					indices = numpy.concatenate((indices, i))
		return opengl.GLVBO(GL_QUADS, verts, indicesArray=indices)

	def _gcodeToVBO_lines(self, gcodeLayers):
		verts = numpy.zeros((0,3), numpy.float32)
		indices = numpy.zeros((0), numpy.uint32)
		for layer in gcodeLayers:
			for path in layer:
				if path['type'] == 'move':
					a = path['points'] + numpy.array([0,0,0.02], numpy.float32)
					i = numpy.arange(len(verts), len(verts) + len(a), 1, numpy.uint32)
					i = numpy.dstack((i[0:-1],i[1:])).flatten()
					verts = numpy.concatenate((verts, a))
					indices = numpy.concatenate((indices, i))
				if path['type'] == 'retract':
					a = path['points'] + numpy.array([0,0,0.02], numpy.float32)
					a = numpy.concatenate((a[:-1], a[1:] + numpy.array([0,0,1], numpy.float32)), 1)
					a = a.reshape((len(a) * 2, 3))
					i = numpy.arange(len(verts), len(verts) + len(a), 1, numpy.uint32)
					verts = numpy.concatenate((verts, a))
					indices = numpy.concatenate((indices, i))
		return opengl.GLVBO(GL_LINES, verts, indicesArray=indices)

	def OnKeyChar(self, keyCode):
		if not self._enabled:
			return

		if wx.GetKeyState(wx.WXK_SHIFT) or wx.GetKeyState(wx.WXK_CONTROL):
			if keyCode == wx.WXK_UP:
				self.layerSelect.setValue(self.layerSelect.getValue() + 1)
				self._parent.QueueRefresh()
				return True
			elif keyCode == wx.WXK_DOWN:
				self.layerSelect.setValue(self.layerSelect.getValue() - 1)
				self._parent.QueueRefresh()
				return True
			elif keyCode == wx.WXK_PAGEUP:
				self.layerSelect.setValue(self.layerSelect.getValue() + 10)
				self._parent.QueueRefresh()
				return True
			elif keyCode == wx.WXK_PAGEDOWN:
				self.layerSelect.setValue(self.layerSelect.getValue() - 10)
				self._parent.QueueRefresh()
				return True
		return False

		# if self.viewMode == 'gcode' and self._gcode is not None:
		# 	try:
		# 		self._viewTarget[2] = self._gcode.layerList[self.layerSelect.getValue()][-1]['points'][0][2]
		# 	except:
		# 		pass

	# def _loadGCode(self):
	# 	self._gcode.progressCallback = self._gcodeLoadCallback
	# 	if self._gcodeFilename is not None:
	# 		self._gcode.load(self._gcodeFilename)
	# 	else:
	# 		self._gcode.load(self._gcodeData)
	#
	# def _gcodeLoadCallback(self, progress):
	# 	if not self or self._gcode is None:
	# 		return True
	# 	if len(self._gcode.layerList) % 15 == 0:
	# 		time.sleep(0.1)
	# 	if self._gcode is None:
	# 		return True
	# 	self.layerSelect.setRange(1, len(self._gcode.layerList) - 1)
	# 	if self.viewMode == 'gcode':
	# 		self._queueRefresh()
	# 	return False

			# if self._gcodeLoadThread is not None and self._gcodeLoadThread.isAlive():
			# 	glDisable(GL_DEPTH_TEST)
			# 	glPushMatrix()
			# 	glLoadIdentity()
			# 	glTranslate(0,-4,-10)
			# 	glColor4ub(60,60,60,255)
			# 	opengl.glDrawStringCenter(_("Loading toolpath for visualization..."))
			# 	glPopMatrix()


# if self._gcode is not None:
# 			self._gcode = None
# 			for layerVBOlist in self._gcodeVBOs:
# 				for vbo in layerVBOlist:
# 					self.glReleaseList.append(vbo)
# 			self._gcodeVBOs = []

			# if self._gcode is not None and self._gcode.layerList is None:
			# 	self._gcodeLoadThread = threading.Thread(target=self._loadGCode)
			# 	self._gcodeLoadThread.daemon = True
			# 	self._gcodeLoadThread.start()
			#

			#
			# if self._gcode is not None and self._gcode.layerList is not None:
			# 	glPushMatrix()
			# 	if profile.getMachineSetting('machine_center_is_zero') != 'True':
			# 		glTranslate(-self._machineSize[0] / 2, -self._machineSize[1] / 2, 0)
			# 	t = time.time()
			# 	drawUpTill = min(len(self._gcode.layerList), self.layerSelect.getValue() + 1)
			# 	for n in xrange(0, drawUpTill):
			# 		c = 1.0 - float(drawUpTill - n) / 15
			# 		c = max(0.3, c)
			# 		if len(self._gcodeVBOs) < n + 1:
			# 			self._gcodeVBOs.append(self._generateGCodeVBOs(self._gcode.layerList[n]))
			# 			if time.time() - t > 0.5:
			# 				self.QueueRefresh()
			# 				break
			# 		#['WALL-OUTER', 'WALL-INNER', 'FILL', 'SUPPORT', 'SKIRT']
			# 		if n == drawUpTill - 1:
			# 			if len(self._gcodeVBOs[n]) < 9:
			# 				self._gcodeVBOs[n] += self._generateGCodeVBOs2(self._gcode.layerList[n])
			# 			glColor3f(c, 0, 0)
			# 			self._gcodeVBOs[n][8].render(GL_QUADS)
			# 			glColor3f(c/2, 0, c)
			# 			self._gcodeVBOs[n][9].render(GL_QUADS)
			# 			glColor3f(0, c, c/2)
			# 			self._gcodeVBOs[n][10].render(GL_QUADS)
			# 			glColor3f(c, 0, 0)
			# 			self._gcodeVBOs[n][11].render(GL_QUADS)
			#
			# 			glColor3f(0, c, 0)
			# 			self._gcodeVBOs[n][12].render(GL_QUADS)
			# 			glColor3f(c/2, c/2, 0.0)
			# 			self._gcodeVBOs[n][13].render(GL_QUADS)
			# 			glColor3f(0, c, c)
			# 			self._gcodeVBOs[n][14].render(GL_QUADS)
			# 			self._gcodeVBOs[n][15].render(GL_QUADS)
			# 			glColor3f(0, 0, c)
			# 			self._gcodeVBOs[n][16].render(GL_LINES)
			# 		else:
			# 			glColor3f(c, 0, 0)
			# 			self._gcodeVBOs[n][0].render(GL_LINES)
			# 			glColor3f(c/2, 0, c)
			# 			self._gcodeVBOs[n][1].render(GL_LINES)
			# 			glColor3f(0, c, c/2)
			# 			self._gcodeVBOs[n][2].render(GL_LINES)
			# 			glColor3f(c, 0, 0)
			# 			self._gcodeVBOs[n][3].render(GL_LINES)
			#
			# 			glColor3f(0, c, 0)
			# 			self._gcodeVBOs[n][4].render(GL_LINES)
			# 			glColor3f(c/2, c/2, 0.0)
			# 			self._gcodeVBOs[n][5].render(GL_LINES)
			# 			glColor3f(0, c, c)
			# 			self._gcodeVBOs[n][6].render(GL_LINES)
			# 			self._gcodeVBOs[n][7].render(GL_LINES)
			# 	glPopMatrix()
	#
	# def _generateGCodeVBOs(self, layer):
	# 	ret = []
	# 	for extrudeType in ['WALL-OUTER:0', 'WALL-OUTER:1', 'WALL-OUTER:2', 'WALL-OUTER:3', 'WALL-INNER', 'FILL', 'SUPPORT', 'SKIRT']:
	# 		if ':' in extrudeType:
	# 			extruder = int(extrudeType[extrudeType.find(':')+1:])
	# 			extrudeType = extrudeType[0:extrudeType.find(':')]
	# 		else:
	# 			extruder = None
	# 		pointList = numpy.zeros((0,3), numpy.float32)
	# 		for path in layer:
	# 			if path['type'] == 'extrude' and path['pathType'] == extrudeType and (extruder is None or path['extruder'] == extruder):
	# 				a = path['points']
	# 				a = numpy.concatenate((a[:-1], a[1:]), 1)
	# 				a = a.reshape((len(a) * 2, 3))
	# 				pointList = numpy.concatenate((pointList, a))
	# 		ret.append(opengl.GLVBO(pointList))
	# 	return ret
	#
	# def _generateGCodeVBOs2(self, layer):
	# 	filamentRadius = profile.getProfileSettingFloat('filament_diameter') / 2
	# 	filamentArea = math.pi * filamentRadius * filamentRadius
	# 	useFilamentArea = profile.getMachineSetting('gcode_flavor') == 'UltiGCode'
	#
	# 	ret = []
	# 	for extrudeType in ['WALL-OUTER:0', 'WALL-OUTER:1', 'WALL-OUTER:2', 'WALL-OUTER:3', 'WALL-INNER', 'FILL', 'SUPPORT', 'SKIRT']:
	# 		if ':' in extrudeType:
	# 			extruder = int(extrudeType[extrudeType.find(':')+1:])
	# 			extrudeType = extrudeType[0:extrudeType.find(':')]
	# 		else:
	# 			extruder = None
	# 		pointList = numpy.zeros((0,3), numpy.float32)
	# 		for path in layer:
	# 			if path['type'] == 'extrude' and path['pathType'] == extrudeType and (extruder is None or path['extruder'] == extruder):
	# 				a = path['points']
	# 				if extrudeType == 'FILL':
	# 					a[:,2] += 0.01
	#
	# 				normal = a[1:] - a[:-1]
	# 				lens = numpy.sqrt(normal[:,0]**2 + normal[:,1]**2)
	# 				normal[:,0], normal[:,1] = -normal[:,1] / lens, normal[:,0] / lens
	# 				normal[:,2] /= lens
	#
	# 				ePerDist = path['extrusion'][1:] / lens
	# 				if useFilamentArea:
	# 					lineWidth = ePerDist / path['layerThickness'] / 2.0
	# 				else:
	# 					lineWidth = ePerDist * (filamentArea / path['layerThickness'] / 2)
	#
	# 				normal[:,0] *= lineWidth
	# 				normal[:,1] *= lineWidth
	#
	# 				b = numpy.zeros((len(a)-1, 0), numpy.float32)
	# 				b = numpy.concatenate((b, a[1:] + normal), 1)
	# 				b = numpy.concatenate((b, a[1:] - normal), 1)
	# 				b = numpy.concatenate((b, a[:-1] - normal), 1)
	# 				b = numpy.concatenate((b, a[:-1] + normal), 1)
	# 				b = b.reshape((len(b) * 4, 3))
	#
	# 				if len(a) > 2:
	# 					normal2 = normal[:-1] + normal[1:]
	# 					lens2 = numpy.sqrt(normal2[:,0]**2 + normal2[:,1]**2)
	# 					normal2[:,0] /= lens2
	# 					normal2[:,1] /= lens2
	# 					normal2[:,0] *= lineWidth[:-1]
	# 					normal2[:,1] *= lineWidth[:-1]
	#
	# 					c = numpy.zeros((len(a)-2, 0), numpy.float32)
	# 					c = numpy.concatenate((c, a[1:-1]), 1)
	# 					c = numpy.concatenate((c, a[1:-1]+normal[1:]), 1)
	# 					c = numpy.concatenate((c, a[1:-1]+normal2), 1)
	# 					c = numpy.concatenate((c, a[1:-1]+normal[:-1]), 1)
	#
	# 					c = numpy.concatenate((c, a[1:-1]), 1)
	# 					c = numpy.concatenate((c, a[1:-1]-normal[1:]), 1)
	# 					c = numpy.concatenate((c, a[1:-1]-normal2), 1)
	# 					c = numpy.concatenate((c, a[1:-1]-normal[:-1]), 1)
	#
	# 					c = c.reshape((len(c) * 8, 3))
	#
	# 					pointList = numpy.concatenate((pointList, b, c))
	# 				else:
	# 					pointList = numpy.concatenate((pointList, b))
	# 		ret.append(opengl.GLVBO(pointList))
	#
	# 	pointList = numpy.zeros((0,3), numpy.float32)
	# 	for path in layer:
	# 		if path['type'] == 'move':
	# 			a = path['points'] + numpy.array([0,0,0.01], numpy.float32)
	# 			a = numpy.concatenate((a[:-1], a[1:]), 1)
	# 			a = a.reshape((len(a) * 2, 3))
	# 			pointList = numpy.concatenate((pointList, a))
	# 		if path['type'] == 'retract':
	# 			a = path['points'] + numpy.array([0,0,0.01], numpy.float32)
	# 			a = numpy.concatenate((a[:-1], a[1:] + numpy.array([0,0,1], numpy.float32)), 1)
	# 			a = a.reshape((len(a) * 2, 3))
	# 			pointList = numpy.concatenate((pointList, a))
	# 	ret.append(opengl.GLVBO(pointList))
	#
	# 	return ret