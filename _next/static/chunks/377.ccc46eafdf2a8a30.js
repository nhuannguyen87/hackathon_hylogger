"use strict";(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[377],{3862:function(t,i,e){e.d(i,{Z:function(){return h}});var o=e(2774),n=e(5915),r=e(7517),s=e(5022),l=e(9931),a=e(3746),c=e(9335);let g="layout(std140) uniform lineUniforms {\n  float widthScale;\n  float widthMinPixels;\n  float widthMaxPixels;\n  float useShortestPath;\n  highp int widthUnits;\n} line;\n",p={name:"line",source:"",vs:g,fs:g,uniformTypes:{widthScale:"f32",widthMinPixels:"f32",widthMaxPixels:"f32",useShortestPath:"f32",widthUnits:"i32"}},d={getSourcePosition:{type:"accessor",value:t=>t.sourcePosition},getTargetPosition:{type:"accessor",value:t=>t.targetPosition},getColor:{type:"accessor",value:[0,0,0,255]},getWidth:{type:"accessor",value:1},widthUnits:"pixels",widthScale:{type:"number",value:1,min:0},widthMinPixels:{type:"number",value:0,min:0},widthMaxPixels:{type:"number",value:Number.MAX_SAFE_INTEGER,min:0},antialiasing:!1};class u extends o.Z{getBounds(){var t;return null===(t=this.getAttributeManager())||void 0===t?void 0:t.getBounds(["instanceSourcePositions","instanceTargetPositions"])}getShaders(){let{antialiasing:t}=this.props;return super.getShaders({vs:"#version 300 es\n#define SHADER_NAME line-layer-vertex-shader\nin vec3 positions;\nin vec3 instanceSourcePositions;\nin vec3 instanceTargetPositions;\nin vec3 instanceSourcePositions64Low;\nin vec3 instanceTargetPositions64Low;\nin vec4 instanceColors;\nin float instanceWidths;\nout vec4 vColor;\nout vec2 uv;\nvec2 getExtrusionOffset(vec2 line_clipspace, float offset_direction, float width) {\nvec2 dir_screenspace = normalize(line_clipspace * project.viewportSize);\ndir_screenspace = vec2(-dir_screenspace.y, dir_screenspace.x);\nreturn dir_screenspace * offset_direction * width / 2.0;\n}\nvec3 splitLine(vec3 a, vec3 b, float x) {\nfloat t = (x - a.x) / (b.x - a.x);\nreturn vec3(x, mix(a.yz, b.yz, t));\n}\nvoid main(void) {\ngeometry.worldPosition = instanceSourcePositions;\ngeometry.worldPositionAlt = instanceTargetPositions;\nvec3 source_world = instanceSourcePositions;\nvec3 target_world = instanceTargetPositions;\nvec3 source_world_64low = instanceSourcePositions64Low;\nvec3 target_world_64low = instanceTargetPositions64Low;\nif (line.useShortestPath > 0.5 || line.useShortestPath < -0.5) {\nsource_world.x = mod(source_world.x + 180., 360.0) - 180.;\ntarget_world.x = mod(target_world.x + 180., 360.0) - 180.;\nfloat deltaLng = target_world.x - source_world.x;\nif (deltaLng * line.useShortestPath > 180.) {\nsource_world.x += 360. * line.useShortestPath;\nsource_world = splitLine(source_world, target_world, 180. * line.useShortestPath);\nsource_world_64low = vec3(0.0);\n} else if (deltaLng * line.useShortestPath < -180.) {\ntarget_world.x += 360. * line.useShortestPath;\ntarget_world = splitLine(source_world, target_world, 180. * line.useShortestPath);\ntarget_world_64low = vec3(0.0);\n} else if (line.useShortestPath < 0.) {\ngl_Position = vec4(0.);\nreturn;\n}\n}\nvec4 source_commonspace;\nvec4 target_commonspace;\nvec4 source = project_position_to_clipspace(source_world, source_world_64low, vec3(0.), source_commonspace);\nvec4 target = project_position_to_clipspace(target_world, target_world_64low, vec3(0.), target_commonspace);\nfloat segmentIndex = positions.x;\nvec4 p = mix(source, target, segmentIndex);\ngeometry.position = mix(source_commonspace, target_commonspace, segmentIndex);\nuv = positions.xy;\ngeometry.uv = uv;\ngeometry.pickingColor = picking_getPickingColorFromInstanceID();\nfloat widthPixels = clamp(\nproject_size_to_pixel(instanceWidths * line.widthScale, line.widthUnits),\nline.widthMinPixels, line.widthMaxPixels\n);\nvec3 offset = vec3(\ngetExtrusionOffset(target.xy - source.xy, positions.y, widthPixels),\n0.0);\nDECKGL_FILTER_SIZE(offset, geometry);\n#ifdef ANTIALIASING\nfloat halfWidthPixels = length(offset.xy);\nif (halfWidthPixels > 0.0) {\nfloat coverageScale = 1.0 + 0.5 / project.devicePixelRatio / halfWidthPixels;\noffset.xy *= coverageScale;\nuv.y *= coverageScale;\n}\ngeometry.uv = uv;\n#endif\nDECKGL_FILTER_GL_POSITION(p, geometry);\ngl_Position = p + vec4(project_pixel_size_to_clipspace(offset.xy), 0.0, 0.0);\nvColor = vec4(instanceColors.rgb, instanceColors.a * layer.opacity);\nDECKGL_FILTER_COLOR(vColor, geometry);\n}\n",fs:"#version 300 es\n#define SHADER_NAME line-layer-fragment-shader\nprecision highp float;\nin vec4 vColor;\nin vec2 uv;\nout vec4 fragColor;\nvoid main(void) {\ngeometry.uv = uv;\nfragColor = vColor;\n#ifdef ANTIALIASING\nfloat edgeCoord = abs(uv.y);\nfloat edgePixels = (1.0 - edgeCoord) / max(fwidth(edgeCoord), 1e-6);\nif (edgePixels <= -SMOOTH_EDGE_RADIUS) {\ndiscard;\n}\nfragColor.a *= smoothedge(0.0, edgePixels);\n#endif\nDECKGL_FILTER_COLOR(fragColor, geometry);\n}\n",source:'// ---------- Helper Structures & Functions ----------\n\n// Placeholder filter functions.\nfn deckgl_filter_size(offset: vec3<f32>, geometry: Geometry) -> vec3<f32> {\n  return offset;\n}\nfn deckgl_filter_gl_position(p: vec4<f32>, geometry: Geometry) -> vec4<f32> {\n  if (picking.isAttribute > 0.5) {\n    // For depth picking, write normalized depth into the picking payload.\n    // This mirrors the legacy DECKGL_FILTER_GL_POSITION hook on WebGL.\n  }\n  return p;\n}\n\n// Compute an extrusion offset given a line direction (in clipspace),\n// an offset direction (-1 or 1), and a width in pixels.\n// Assumes a uniform "project" with a viewportSize field is available.\nfn getExtrusionOffset(line_clipspace: vec2<f32>, offset_direction: f32, width: f32) -> vec2<f32> {\n  // project.viewportSize should be provided as a uniform (not shown here)\n  let dir_screenspace = normalize(line_clipspace * project.viewportSize);\n  // Rotate by 90\xb0: (x,y) becomes (-y,x)\n  let rotated = vec2<f32>(-dir_screenspace.y, dir_screenspace.x);\n  return rotated * offset_direction * width / 2.0;\n}\n\n// Splits the line between two points at a given x coordinate.\n// Interpolates the y and z components.\nfn splitLine(a: vec3<f32>, b: vec3<f32>, x: f32) -> vec3<f32> {\n  let t: f32 = (x - a.x) / (b.x - a.x);\n  return vec3<f32>(x, a.yz + t * (b.yz - a.yz));\n}\n\n// ---------- Uniforms & Global Structures ----------\n\nstruct LineUniforms {\n  widthScale: f32,\n  widthMinPixels: f32,\n  widthMaxPixels: f32,\n  useShortestPath: f32,\n  widthUnits: i32,\n};\n\n@group(0) @binding(0)\nvar<uniform> line: LineUniforms;\n\n\n\n// ---------- Vertex Output Structure ----------\n\nstruct Varyings {\n  @builtin(position) gl_Position: vec4<f32>,\n  @location(0) vColor: vec4<f32>,\n  @location(1) uv: vec2<f32>,\n  @location(2) pickingColor: vec3<f32>,\n};\n\n// ---------- Vertex Shader Entry Point ----------\n\n@vertex\nfn vertexMain(\n  @builtin(instance_index) instanceIndex: u32,\n  @location(0) positions: vec3<f32>,\n  @location(1) instanceSourcePositions: vec3<f32>,\n  @location(2) instanceTargetPositions: vec3<f32>,\n  @location(3) instanceSourcePositions64Low: vec3<f32>,\n  @location(4) instanceTargetPositions64Low: vec3<f32>,\n  @location(5) instanceColors: vec4<f32>,\n  @location(6) instanceWidths: f32\n) -> Varyings {\n  geometry.worldPosition = instanceSourcePositions;\n  geometry.worldPositionAlt = instanceTargetPositions;\n\n  var source_world: vec3<f32> = instanceSourcePositions;\n  var target_world: vec3<f32> = instanceTargetPositions;\n  var source_world_64low: vec3<f32> = instanceSourcePositions64Low;\n  var target_world_64low: vec3<f32> = instanceTargetPositions64Low;\n\n  // Apply shortest-path adjustments if needed.\n  if (line.useShortestPath > 0.5 || line.useShortestPath < -0.5) {\n    source_world.x = (source_world.x + 180.0 % 360.0) - 180.0;\n    target_world.x = (target_world.x + 180.0 % 360.0) - 180.0;\n    let deltaLng: f32 = target_world.x - source_world.x;\n\n    if (deltaLng * line.useShortestPath > 180.0) {\n      source_world.x = source_world.x + 360.0 * line.useShortestPath;\n      source_world = splitLine(source_world, target_world, 180.0 * line.useShortestPath);\n      source_world_64low = vec3<f32>(0.0, 0.0, 0.0);\n    } else if (deltaLng * line.useShortestPath < -180.0) {\n      target_world.x = target_world.x + 360.0 * line.useShortestPath;\n      target_world = splitLine(source_world, target_world, 180.0 * line.useShortestPath);\n      target_world_64low = vec3<f32>(0.0, 0.0, 0.0);\n    } else if (line.useShortestPath < 0.0) {\n      var abortOut: Varyings;\n      abortOut.gl_Position = vec4<f32>(0.0);\n      abortOut.vColor = vec4<f32>(0.0);\n      abortOut.uv = vec2<f32>(0.0);\n      return abortOut;\n    }\n  }\n\n  // Project Pos and target positions to clip space.\n  let sourceResult = project_position_to_clipspace_and_commonspace(source_world, source_world_64low, vec3<f32>(0.0));\n  let targetResult = project_position_to_clipspace_and_commonspace(target_world, target_world_64low, vec3<f32>(0.0));\n  let sourcePos: vec4<f32> = sourceResult.clipPosition;\n  let targetPos: vec4<f32> = targetResult.clipPosition;\n  let source_commonspace: vec4<f32> = sourceResult.commonPosition;\n  let target_commonspace: vec4<f32> = targetResult.commonPosition;\n\n  // Interpolate along the line segment.\n  let segmentIndex: f32 = positions.x;\n  let p: vec4<f32> = sourcePos + segmentIndex * (targetPos - sourcePos);\n  geometry.position = source_commonspace + segmentIndex * (target_commonspace - source_commonspace);\n#ifdef ANTIALIASING\n  var uv: vec2<f32> = positions.xy;\n#else\n  let uv: vec2<f32> = positions.xy;\n#endif\n  geometry.uv = uv;\n  geometry.pickingColor = picking_getPickingColorFromIndex(instanceIndex);\n\n  // Determine width in pixels.\n  let widthPixels: f32 = clamp(\n    project_unit_size_to_pixel(instanceWidths * line.widthScale, line.widthUnits),\n    line.widthMinPixels, line.widthMaxPixels\n  );\n\n  // Compute extrusion offset.\n  let extrusion: vec2<f32> = getExtrusionOffset(targetPos.xy - sourcePos.xy, positions.y, widthPixels);\n  let offset: vec3<f32> = vec3<f32>(extrusion, 0.0);\n\n  // Apply deck.gl filter functions.\n#ifdef ANTIALIASING\n  var filteredOffset = deckgl_filter_size(offset, geometry);\n  let halfWidthPixels = length(filteredOffset.xy);\n  if (halfWidthPixels > 0.0) {\n    // Keep the declared edge at abs(uv.y) == 1 while rasterizing the outer half of the centered\n    // one-device-pixel coverage ramp.\n    let coverageScale = 1.0 + 0.5 / project.devicePixelRatio / halfWidthPixels;\n    filteredOffset *= coverageScale;\n    uv.y *= coverageScale;\n  }\n  geometry.uv = uv;\n#else\n  let filteredOffset = deckgl_filter_size(offset, geometry);\n#endif\n  let filteredP = deckgl_filter_gl_position(p, geometry);\n\n  let clipOffset: vec2<f32> = project_pixel_size_to_clipspace(filteredOffset.xy);\n  let finalPosition: vec4<f32> = filteredP + vec4<f32>(clipOffset, 0.0, 0.0);\n\n  // Compute color.\n  var vColor: vec4<f32> = vec4<f32>(instanceColors.rgb, instanceColors.a * layer.opacity);\n  // vColor = deckgl_filter_color(vColor, geometry);\n\n  var output: Varyings;\n  output.gl_Position = finalPosition;\n  output.vColor = vColor;\n  output.uv = uv;\n  output.pickingColor = geometry.pickingColor;\n  return output;\n}\n\n@fragment\nfn fragmentMain(\n  @location(0) vColor: vec4<f32>,\n  @location(1) uv: vec2<f32>,\n  @location(2) pickingColor: vec3<f32>\n) -> @location(0) vec4<f32> {\n  // Create and initialize geometry with the provided uv.\n  var geometry: Geometry;\n  geometry.uv = uv;\n\n  // Start with the input color.\n  var fragColor: vec4<f32> = vColor;\n\n#ifdef ANTIALIASING\n  // Distance to the edge in device pixels, from the derivative of uv.y. Taken in uniform control\n  // flow, ahead of the picking discard below\n  let edgeCoord = abs(uv.y);\n  let edgePixels = (1.0 - edgeCoord) / max(fwidth(edgeCoord), 1e-6);\n\n  // Fragments outside the coverage ramp must not write depth or picking colors.\n  if (edgePixels <= -SMOOTH_EDGE_RADIUS) {\n    discard;\n  }\n\n  // Feather one device pixel across the width, before premultiplication below. The ends are left\n  // hard - they abut neighbors\n  fragColor.a *= smoothedge(0.0, edgePixels);\n#endif\n\n  if (picking.isActive > 0.5) {\n    if (!picking_isColorValid(pickingColor)) {\n      discard;\n    }\n    return vec4<f32>(pickingColor, 1.0);\n  }\n\n  if (picking.isHighlightActive > 0.5) {\n    let highlightedObjectColor = picking_normalizeColor(picking.highlightedObjectColor);\n    if (picking_isColorZero(abs(pickingColor - highlightedObjectColor))) {\n      let highLightAlpha = picking.highlightColor.a;\n      let blendedAlpha = highLightAlpha + fragColor.a * (1.0 - highLightAlpha);\n      if (blendedAlpha > 0.0) {\n        let highLightRatio = highLightAlpha / blendedAlpha;\n        fragColor = vec4<f32>(\n          mix(fragColor.rgb, picking.highlightColor.rgb, highLightRatio),\n          blendedAlpha\n        );\n      } else {\n        fragColor = vec4<f32>(fragColor.rgb, 0.0);\n      }\n    }\n  }\n\n  // Apply premultiplied alpha as required by transparent canvas\n  fragColor = deckgl_premultiplied_alpha(fragColor);\n\n  return fragColor;\n}\n',defines:t?{ANTIALIASING:1}:{},modules:[n.Z,r.Z,s.ZP,p]})}get wrapLongitude(){return!1}initializeState(){this.getAttributeManager().addInstanced({instanceSourcePositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getSourcePosition"},instanceTargetPositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getTargetPosition"},instanceColors:{size:this.props.colorFormat.length,type:"unorm8",transition:!0,accessor:"getColor",defaultValue:[0,0,0,255]},instanceWidths:{size:1,transition:!0,accessor:"getWidth",defaultValue:1}})}updateState(t){super.updateState(t);let{props:i,oldProps:e,changeFlags:o}=t;if(o.extensionsChanged||i.antialiasing!==e.antialiasing){var n;null===(n=this.state.model)||void 0===n||n.destroy(),this.state.model=this._getModel(),this.getAttributeManager().invalidateAll()}}draw(t){let{uniforms:i}=t,{widthUnits:e,widthScale:o,widthMinPixels:n,widthMaxPixels:r,wrapLongitude:s}=this.props,a=this.state.model,c={widthUnits:l.iI[e],widthScale:o,widthMinPixels:n,widthMaxPixels:r,useShortestPath:s?1:0};a.shaderInputs.setProps({line:c}),a.draw(this.context.renderPass),s&&(a.shaderInputs.setProps({line:{...c,useShortestPath:-1}}),a.draw(this.context.renderPass))}_getModel(){return new a.H(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),geometry:new c.Z({topology:"triangle-strip",attributes:{positions:{size:3,value:new Float32Array([0,-1,0,0,1,0,1,-1,0,1,1,0])}}}),isInstanced:!0})}}u.layerName="LineLayer",u.defaultProps=d;var h=u},7115:function(t,i,e){e.d(i,{Z:function(){return v}});var o=e(2774),n=e(5915),r=e(7517),s=e(5022),l=e(9931),a=e(3746),c=e(9335);let g="layout(std140) uniform scatterplotUniforms {\n  float radiusScale;\n  float radiusMinPixels;\n  float radiusMaxPixels;\n  float lineWidthScale;\n  float lineWidthMinPixels;\n  float lineWidthMaxPixels;\n  float stroked;\n  float filled;\n  bool antialiasing;\n  bool billboard;\n  highp int radiusUnits;\n  highp int lineWidthUnits;\n} scatterplot;\n",p={name:"scatterplot",vs:g,fs:g,source:"",uniformTypes:{radiusScale:"f32",radiusMinPixels:"f32",radiusMaxPixels:"f32",lineWidthScale:"f32",lineWidthMinPixels:"f32",lineWidthMaxPixels:"f32",stroked:"f32",filled:"f32",antialiasing:"f32",billboard:"f32",radiusUnits:"i32",lineWidthUnits:"i32"}};var d=e(9098);let u=[0,0,0,255],h={radiusUnits:"meters",radiusScale:{type:"number",min:0,value:1},radiusMinPixels:{type:"number",min:0,value:0},radiusMaxPixels:{type:"number",min:0,value:Number.MAX_SAFE_INTEGER},lineWidthUnits:"meters",lineWidthScale:{type:"number",min:0,value:1},lineWidthMinPixels:{type:"number",min:0,value:0},lineWidthMaxPixels:{type:"number",min:0,value:Number.MAX_SAFE_INTEGER},stroked:!1,filled:!0,billboard:!1,antialiasing:!0,getPosition:{type:"accessor",value:t=>t.position},getRadius:{type:"accessor",value:1},getFillColor:{type:"accessor",value:u},getLineColor:{type:"accessor",value:u},getLineWidth:{type:"accessor",value:1},getPixelOffset:{type:"accessor",value:[0,0]},strokeWidth:{deprecatedFor:"getLineWidth"},outline:{deprecatedFor:"stroked"},getColor:{deprecatedFor:["getFillColor","getLineColor"]}};class f extends o.Z{getShaders(){var t,i;let e=!!(null===(i=this.props.data)||void 0===i?void 0:null===(t=i.attributes)||void 0===t?void 0:t.rowIndexes);return super.getShaders({vs:"#version 300 es\n#define SHADER_NAME scatterplot-layer-vertex-shader\nin vec3 positions;\nin vec3 instancePositions;\nin vec3 instancePositions64Low;\nin float instanceRadius;\nin float instanceLineWidths;\nin vec4 instanceFillColors;\nin vec4 instanceLineColors;\n#ifdef USE_ROW_INDEXES\nin float rowIndexes;\n#endif\nin vec2 instancePixelOffset;\nout vec4 vFillColor;\nout vec4 vLineColor;\nout vec2 unitPosition;\nout float innerUnitRadius;\nout float outerRadiusPixels;\nvoid main(void) {\ngeometry.worldPosition = instancePositions;\nouterRadiusPixels = clamp(\nproject_size_to_pixel(scatterplot.radiusScale * instanceRadius, scatterplot.radiusUnits),\nscatterplot.radiusMinPixels, scatterplot.radiusMaxPixels\n);\nfloat lineWidthPixels = clamp(\nproject_size_to_pixel(scatterplot.lineWidthScale * instanceLineWidths, scatterplot.lineWidthUnits),\nscatterplot.lineWidthMinPixels, scatterplot.lineWidthMaxPixels\n);\nouterRadiusPixels += scatterplot.stroked * lineWidthPixels / 2.0;\nfloat edgePadding = scatterplot.antialiasing ? (outerRadiusPixels + SMOOTH_EDGE_RADIUS) / outerRadiusPixels : 1.0;\nunitPosition = edgePadding * positions.xy;\ngeometry.uv = unitPosition;\n#ifdef USE_ROW_INDEXES\ngeometry.pickingColor = picking_getPickingColorFromIndex(rowIndexes);\n#else\ngeometry.pickingColor = picking_getPickingColorFromInstanceID();\n#endif\ninnerUnitRadius = 1.0 - scatterplot.stroked * lineWidthPixels / outerRadiusPixels;\nif (scatterplot.billboard) {\ngl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, vec3(0.0), geometry.position);\nDECKGL_FILTER_GL_POSITION(gl_Position, geometry);\nvec3 offset = edgePadding * positions * outerRadiusPixels;\noffset.xy += instancePixelOffset;\nDECKGL_FILTER_SIZE(offset, geometry);\ngl_Position.xy += project_pixel_size_to_clipspace(offset.xy);\n} else {\nvec3 offset = edgePadding * positions * project_pixel_size(outerRadiusPixels);\noffset.xy += project_pixel_size(instancePixelOffset);\nDECKGL_FILTER_SIZE(offset, geometry);\ngl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, offset, geometry.position);\nDECKGL_FILTER_GL_POSITION(gl_Position, geometry);\n}\nvFillColor = vec4(instanceFillColors.rgb, instanceFillColors.a * layer.opacity);\nDECKGL_FILTER_COLOR(vFillColor, geometry);\nvLineColor = vec4(instanceLineColors.rgb, instanceLineColors.a * layer.opacity);\nDECKGL_FILTER_COLOR(vLineColor, geometry);\n}\n",fs:"#version 300 es\n#define SHADER_NAME scatterplot-layer-fragment-shader\nprecision highp float;\nin vec4 vFillColor;\nin vec4 vLineColor;\nin vec2 unitPosition;\nin float innerUnitRadius;\nin float outerRadiusPixels;\nout vec4 fragColor;\nvoid main(void) {\ngeometry.uv = unitPosition;\nfloat distToCenter = length(unitPosition) * outerRadiusPixels;\nfloat inCircle = scatterplot.antialiasing ?\nsmoothedge(distToCenter, outerRadiusPixels) :\nstep(distToCenter, outerRadiusPixels);\nif (inCircle == 0.0) {\ndiscard;\n}\nif (scatterplot.stroked > 0.5) {\nfloat isLine = scatterplot.antialiasing ?\nsmoothedge(innerUnitRadius * outerRadiusPixels, distToCenter) :\nstep(innerUnitRadius * outerRadiusPixels, distToCenter);\nif (scatterplot.filled > 0.5) {\nfragColor = mix(vFillColor, vLineColor, isLine);\n} else {\nif (isLine == 0.0) {\ndiscard;\n}\nfragColor = vec4(vLineColor.rgb, vLineColor.a * isLine);\n}\n} else if (scatterplot.filled < 0.5) {\ndiscard;\n} else {\nfragColor = vFillColor;\n}\nfragColor.a *= inCircle;\nDECKGL_FILTER_COLOR(fragColor, geometry);\n}\n",source:"// Main shaders\n\nstruct ScatterplotUniforms {\n  radiusScale: f32,\n  radiusMinPixels: f32,\n  radiusMaxPixels: f32,\n  lineWidthScale: f32,\n  lineWidthMinPixels: f32,\n  lineWidthMaxPixels: f32,\n  stroked: f32,\n  filled: i32,\n  antialiasing: i32,\n  billboard: i32,\n  radiusUnits: i32,\n  lineWidthUnits: i32,\n};\n\n@group(0) @binding(0) var<uniform> scatterplot: ScatterplotUniforms;\n\nstruct Attributes {\n  @builtin(instance_index) instanceIndex : u32,\n  @builtin(vertex_index) vertexIndex : u32,\n  @location(0) positions: vec3<f32>,\n  @location(1) instancePositions: vec3<f32>,\n  @location(2) instancePositions64Low: vec3<f32>,\n  @location(3) instanceRadius: f32,\n  @location(4) instanceLineWidths: f32,\n  @location(5) instanceFillColors: vec4<f32>,\n  @location(6) instanceLineColors: vec4<f32>,\n  @location(7) instancePixelOffset: vec2<f32>,\n  PICKING_COLOR_ATTRIBUTE\n};\n\nstruct Varyings {\n  @builtin(position) position: vec4<f32>,\n  @location(0) vFillColor: vec4<f32>,\n  @location(1) vLineColor: vec4<f32>,\n  @location(2) unitPosition: vec2<f32>,\n  @location(3) innerUnitRadius: f32,\n  @location(4) outerRadiusPixels: f32,\n  @location(5) pickingColor: vec3<f32>,\n  @location(6) clipCoordinates: vec2<f32>,\n};\n\n@vertex\nfn vertexMain(attributes: Attributes) -> Varyings {\n  var varyings: Varyings;\n\n  // Draw an inline geometry constant array clip space triangle to verify that rendering works.\n  // var positions = array<vec2<f32>, 3>(vec2(0.0, 0.5), vec2(-0.5, -0.5), vec2(0.5, -0.5));\n  // if (attributes.instanceIndex == 0) {\n  //   varyings.position = vec4<f32>(positions[attributes.vertexIndex], 0.0, 1.0);\n  //   return varyings;\n  // }\n\n  geometry.worldPosition = attributes.instancePositions;\n\n  // Multiply out radius and clamp to limits\n  varyings.outerRadiusPixels = clamp(\n    project_unit_size_to_pixel(scatterplot.radiusScale * attributes.instanceRadius, scatterplot.radiusUnits),\n    scatterplot.radiusMinPixels, scatterplot.radiusMaxPixels\n  );\n\n  // Multiply out line width and clamp to limits\n  let lineWidthPixels = clamp(\n    project_unit_size_to_pixel(scatterplot.lineWidthScale * attributes.instanceLineWidths, scatterplot.lineWidthUnits),\n    scatterplot.lineWidthMinPixels, scatterplot.lineWidthMaxPixels\n  );\n\n  // outer radius needs to offset by half stroke width\n  varyings.outerRadiusPixels += scatterplot.stroked * lineWidthPixels / 2.0;\n  // Expand geometry to accommodate edge smoothing\n  // WGSL selects the second value when the condition is true, so keep the antialiased path second.\n  let edgePadding = select(\n    1.0,\n    (varyings.outerRadiusPixels + SMOOTH_EDGE_RADIUS) / varyings.outerRadiusPixels,\n    scatterplot.antialiasing != 0\n  );\n\n  // position on the containing square in [-1, 1] space\n  varyings.unitPosition = edgePadding * attributes.positions.xy;\n  geometry.uv = varyings.unitPosition;\n  geometry.pickingColor = PICKING_COLOR_VALUE;\n\n  varyings.innerUnitRadius = 1.0 - scatterplot.stroked * lineWidthPixels / varyings.outerRadiusPixels;\n\n  if (scatterplot.billboard != 0) {\n    let projectedPosition = project_position_to_clipspace_and_commonspace(\n      attributes.instancePositions,\n      attributes.instancePositions64Low,\n      vec3<f32>(0.0)\n    );\n    geometry.position = projectedPosition.commonPosition;\n    varyings.position = projectedPosition.clipPosition;\n    // DECKGL_FILTER_GL_POSITION(varyings.position, geometry);\n    var offset = edgePadding * attributes.positions * varyings.outerRadiusPixels;\n    offset = vec3<f32>(offset.xy + attributes.instancePixelOffset, offset.z);\n    // DECKGL_FILTER_SIZE(offset, geometry);\n    let clipPixels = project_pixel_size_to_clipspace(offset.xy);\n    varyings.position = vec4<f32>(varyings.position.x + clipPixels.x, varyings.position.y + clipPixels.y, varyings.position.z, varyings.position.w);\n    geometry.position = vec4<f32>(\n      geometry.position.xy + project_pixel_size_vec2(offset.xy),\n      geometry.position.zw\n    );\n  } else {\n    var offset = edgePadding * attributes.positions * project_pixel_size_float(varyings.outerRadiusPixels);\n    offset = vec3<f32>(offset.xy + project_pixel_size_vec2(attributes.instancePixelOffset), offset.z);\n    // DECKGL_FILTER_SIZE(offset, geometry);\n    let projectedPosition = project_position_to_clipspace_and_commonspace(\n      attributes.instancePositions,\n      attributes.instancePositions64Low,\n      offset\n    );\n    geometry.position = projectedPosition.commonPosition;\n    varyings.position = projectedPosition.clipPosition;\n    // DECKGL_FILTER_GL_POSITION(varyings.position, geometry);\n  }\n\n  varyings.clipCoordinates = geometry.position.xy;\n  clip_filterPosition(&varyings.position, geometry.worldPosition.xy);\n\n  // Apply opacity to instance color, or return instance picking color\n  varyings.vFillColor = vec4<f32>(attributes.instanceFillColors.rgb, attributes.instanceFillColors.a * layer.opacity);\n  // DECKGL_FILTER_COLOR(varyings.vFillColor, geometry);\n  varyings.vLineColor = vec4<f32>(attributes.instanceLineColors.rgb, attributes.instanceLineColors.a * layer.opacity);\n  // DECKGL_FILTER_COLOR(varyings.vLineColor, geometry);\n  varyings.pickingColor = geometry.pickingColor;\n\n  return varyings;\n}\n\n@fragment\nfn fragmentMain(varyings: Varyings) -> @location(0) vec4<f32> {\n  // var geometry: Geometry;\n  // geometry.uv = unitPosition;\n\n  let distToCenter = length(varyings.unitPosition) * varyings.outerRadiusPixels;\n  let inCircle = select(\n    step(distToCenter, varyings.outerRadiusPixels),\n    smoothedge(distToCenter, varyings.outerRadiusPixels),\n    scatterplot.antialiasing != 0\n  );\n\n  if (inCircle == 0.0) {\n    discard;\n  }\n\n  var fragColor: vec4<f32>;\n\n  if (scatterplot.stroked != 0) {\n    let isLine = select(\n      step(varyings.innerUnitRadius * varyings.outerRadiusPixels, distToCenter),\n      smoothedge(varyings.innerUnitRadius * varyings.outerRadiusPixels, distToCenter),\n      scatterplot.antialiasing != 0\n    );\n\n    if (scatterplot.filled != 0) {\n      fragColor = mix(varyings.vFillColor, varyings.vLineColor, isLine);\n    } else {\n      if (isLine == 0.0) {\n        discard;\n      }\n      fragColor = vec4<f32>(varyings.vLineColor.rgb, varyings.vLineColor.a * isLine);\n    }\n  } else if (scatterplot.filled == 0) {\n    discard;\n  } else {\n    fragColor = varyings.vFillColor;\n  }\n\n  fragColor.a *= inCircle;\n\n  clip_filterColor(varyings.clipCoordinates);\n\n  if (picking.isActive > 0.5) {\n    if (!picking_isColorValid(varyings.pickingColor)) {\n      discard;\n    }\n    return vec4<f32>(varyings.pickingColor, 1.0);\n  }\n\n  if (picking.isHighlightActive > 0.5) {\n    let highlightedObjectColor = picking_normalizeColor(picking.highlightedObjectColor);\n    if (picking_isColorZero(abs(varyings.pickingColor - highlightedObjectColor))) {\n      let highLightAlpha = picking.highlightColor.a;\n      let blendedAlpha = highLightAlpha + fragColor.a * (1.0 - highLightAlpha);\n      if (blendedAlpha > 0.0) {\n        let highLightRatio = highLightAlpha / blendedAlpha;\n        fragColor = vec4<f32>(\n          mix(fragColor.rgb, picking.highlightColor.rgb, highLightRatio),\n          blendedAlpha\n        );\n      } else {\n        fragColor = vec4<f32>(fragColor.rgb, 0.0);\n      }\n    }\n  }\n\n  // Apply premultiplied alpha as required by transparent canvas\n  fragColor = deckgl_premultiplied_alpha(fragColor);\n\n  return fragColor;\n  // return vec4<f32>(0, 0, 1, 1);\n}\n".replace("PICKING_COLOR_ATTRIBUTE",e?"@location(8) rowIndexes: u32,":"").replace("PICKING_COLOR_VALUE",e?"picking_getPickingColorFromIndex(attributes.rowIndexes)":"picking_getPickingColorFromIndex(attributes.instanceIndex)"),defines:e?{USE_ROW_INDEXES:!0}:{},modules:[n.Z,r.Z,s.ZP,p,..."webgpu"===this.context.device.type?[d.Z]:[]]})}initializeState(){var t,i;let e=(null===(i=this.props.data)||void 0===i?void 0:null===(t=i.attributes)||void 0===t?void 0:t.rowIndexes)?{rowIndexes:{size:1,type:"uint32",noAlloc:!0}}:{};this.getAttributeManager().addInstanced({instancePositions:{size:3,type:"float64",fp64:this.use64bitPositions(),transition:!0,accessor:"getPosition"},instanceRadius:{size:1,transition:!0,accessor:"getRadius",defaultValue:1,bufferGroup:"scatterplot-instance-data"},instanceFillColors:{size:this.props.colorFormat.length,transition:!0,type:"unorm8",accessor:"getFillColor",defaultValue:[0,0,0,255],bufferGroup:"scatterplot-instance-data"},instanceLineColors:{size:this.props.colorFormat.length,transition:!0,type:"unorm8",accessor:"getLineColor",defaultValue:[0,0,0,255],bufferGroup:"scatterplot-instance-data"},instanceLineWidths:{size:1,transition:!0,accessor:"getLineWidth",defaultValue:1,bufferGroup:"scatterplot-instance-data"},instancePixelOffset:{size:2,transition:!0,accessor:"getPixelOffset",bufferGroup:"scatterplot-instance-data"},...e})}updateState(t){if(super.updateState(t),t.changeFlags.extensionsChanged){var i;null===(i=this.state.model)||void 0===i||i.destroy(),this.state.model=this._getModel(),this.getAttributeManager().invalidateAll()}}draw(t){let{uniforms:i}=t,{radiusUnits:e,radiusScale:o,radiusMinPixels:n,radiusMaxPixels:r,stroked:s,filled:a,billboard:c,antialiasing:g,lineWidthUnits:p,lineWidthScale:d,lineWidthMinPixels:u,lineWidthMaxPixels:h}=this.props,f={stroked:s,filled:a,billboard:c,antialiasing:g,radiusUnits:l.iI[e],radiusScale:o,radiusMinPixels:n,radiusMaxPixels:r,lineWidthUnits:l.iI[p],lineWidthScale:d,lineWidthMinPixels:u,lineWidthMaxPixels:h},v=this.state.model;v.shaderInputs.setProps({scatterplot:f}),v.draw(this.context.renderPass)}_getModel(){return new a.H(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),geometry:new c.Z({topology:"triangle-strip",attributes:{positions:{size:3,value:new Float32Array([-1,-1,0,1,-1,0,-1,1,0,1,1,0])}}}),isInstanced:!0})}}f.defaultProps=h,f.layerName="ScatterplotLayer";var v=f},5405:function(t,i,e){e.d(i,{Z:function(){return U}});var o=e(9577),n=e(2774),r=e(5915),s=e(7517);Uint32Array.BYTES_PER_ELEMENT,c("colors");let l=c("floatColors");g("colors");let a=g("floatColors");function c(t){return`\
layout(std140) uniform ${t}Uniforms {
  float useByteColors;
} ${t};

vec3 ${t}_normalize(vec3 inputColor) {
  return ${t}.useByteColors > 0.5 ? inputColor / 255.0 : inputColor;
}

vec4 ${t}_normalize(vec4 inputColor) {
  return ${t}.useByteColors > 0.5 ? inputColor / 255.0 : inputColor;
}

vec4 ${t}_premultiplyAlpha(vec4 inputColor) {
  return vec4(inputColor.rgb * inputColor.a, inputColor.a);
}

vec4 ${t}_unpremultiplyAlpha(vec4 inputColor) {
  return inputColor.a > 0.0 ? vec4(inputColor.rgb / inputColor.a, inputColor.a) : vec4(0.0);
}

vec4 ${t}_premultiply_alpha(vec4 inputColor) {
  return ${t}_premultiplyAlpha(inputColor);
}

vec4 ${t}_unpremultiply_alpha(vec4 inputColor) {
  return ${t}_unpremultiplyAlpha(inputColor);
}
`}function g(t){return`\
struct ${t}Uniforms {
  useByteColors: f32
};

@group(0) @binding(auto) var<uniform> ${t} : ${t}Uniforms;

fn ${t}_normalize(inputColor: vec3<f32>) -> vec3<f32> {
  return select(inputColor, inputColor / 255.0, ${t}.useByteColors > 0.5);
}

fn ${t}_normalize4(inputColor: vec4<f32>) -> vec4<f32> {
  return select(inputColor, inputColor / 255.0, ${t}.useByteColors > 0.5);
}

fn ${t}_premultiplyAlpha(inputColor: vec4<f32>) -> vec4<f32> {
  return vec4<f32>(inputColor.rgb * inputColor.a, inputColor.a);
}

fn ${t}_unpremultiplyAlpha(inputColor: vec4<f32>) -> vec4<f32> {
  return select(
    vec4<f32>(0.0),
    vec4<f32>(inputColor.rgb / inputColor.a, inputColor.a),
    inputColor.a > 0.0
  );
}

fn ${t}_premultiply_alpha(inputColor: vec4<f32>) -> vec4<f32> {
  return ${t}_premultiplyAlpha(inputColor);
}

fn ${t}_unpremultiply_alpha(inputColor: vec4<f32>) -> vec4<f32> {
  return ${t}_unpremultiplyAlpha(inputColor);
}
`}var p=e(8980);let d=`\
precision highp int;

// #if (defined(SHADER_TYPE_FRAGMENT) && defined(LIGHTING_FRAGMENT)) || (defined(SHADER_TYPE_VERTEX) && defined(LIGHTING_VERTEX))
struct AmbientLight {
  vec3 color;
};

struct PointLight {
  vec3 color;
  vec3 position;
  vec3 attenuation; // 2nd order x:Constant-y:Linear-z:Exponential
};

struct SpotLight {
  vec3 color;
  vec3 position;
  vec3 direction;
  vec3 attenuation;
  vec2 coneCos;
};

struct DirectionalLight {
  vec3 color;
  vec3 direction;
};

struct UniformLight {
  vec3 color;
  vec3 position;
  vec3 direction;
  vec3 attenuation;
  vec2 coneCos;
};

layout(std140) uniform lightingUniforms {
  int enabled;
  int directionalLightCount;
  int pointLightCount;
  int spotLightCount;
  vec3 ambientColor;
  UniformLight lights[5];
} lighting;

PointLight lighting_getPointLight(int index) {
  UniformLight light = lighting.lights[index];
  return PointLight(light.color, light.position, light.attenuation);
}

SpotLight lighting_getSpotLight(int index) {
  UniformLight light = lighting.lights[lighting.pointLightCount + index];
  return SpotLight(light.color, light.position, light.direction, light.attenuation, light.coneCos);
}

DirectionalLight lighting_getDirectionalLight(int index) {
  UniformLight light =
    lighting.lights[lighting.pointLightCount + lighting.spotLightCount + index];
  return DirectionalLight(light.color, light.direction);
}

float getPointLightAttenuation(PointLight pointLight, float distance) {
  return pointLight.attenuation.x
       + pointLight.attenuation.y * distance
       + pointLight.attenuation.z * distance * distance;
}

float getSpotLightAttenuation(SpotLight spotLight, vec3 positionWorldspace) {
  vec3 light_direction = normalize(positionWorldspace - spotLight.position);
  float coneFactor = smoothstep(
    spotLight.coneCos.y,
    spotLight.coneCos.x,
    dot(normalize(spotLight.direction), light_direction)
  );
  float distanceAttenuation = getPointLightAttenuation(
    PointLight(spotLight.color, spotLight.position, spotLight.attenuation),
    distance(spotLight.position, positionWorldspace)
  );
  return distanceAttenuation / max(coneFactor, 0.0001);
}

// #endif
`,u=`\
// #if (defined(SHADER_TYPE_FRAGMENT) && defined(LIGHTING_FRAGMENT)) || (defined(SHADER_TYPE_VERTEX) && defined(LIGHTING_VERTEX))
const MAX_LIGHTS: i32 = 5;

struct AmbientLight {
  color: vec3<f32>,
};

struct PointLight {
  color: vec3<f32>,
  position: vec3<f32>,
  attenuation: vec3<f32>, // 2nd order x:Constant-y:Linear-z:Exponential
};

struct SpotLight {
  color: vec3<f32>,
  position: vec3<f32>,
  direction: vec3<f32>,
  attenuation: vec3<f32>,
  coneCos: vec2<f32>,
};

struct DirectionalLight {
  color: vec3<f32>,
  direction: vec3<f32>,
};

struct UniformLight {
  color: vec3<f32>,
  position: vec3<f32>,
  direction: vec3<f32>,
  attenuation: vec3<f32>,
  coneCos: vec2<f32>,
};

struct lightingUniforms {
  enabled: i32,
  directionalLightCount: i32,
  pointLightCount: i32,
  spotLightCount: i32,
  ambientColor: vec3<f32>,
  lights: array<UniformLight, 5>,
};

@group(2) @binding(auto) var<uniform> lighting : lightingUniforms;

fn lighting_getPointLight(index: i32) -> PointLight {
  let light = lighting.lights[index];
  return PointLight(light.color, light.position, light.attenuation);
}

fn lighting_getSpotLight(index: i32) -> SpotLight {
  let light = lighting.lights[lighting.pointLightCount + index];
  return SpotLight(light.color, light.position, light.direction, light.attenuation, light.coneCos);
}

fn lighting_getDirectionalLight(index: i32) -> DirectionalLight {
  let light = lighting.lights[lighting.pointLightCount + lighting.spotLightCount + index];
  return DirectionalLight(light.color, light.direction);
}

fn getPointLightAttenuation(pointLight: PointLight, distance: f32) -> f32 {
  return pointLight.attenuation.x
       + pointLight.attenuation.y * distance
       + pointLight.attenuation.z * distance * distance;
}

fn getSpotLightAttenuation(spotLight: SpotLight, positionWorldspace: vec3<f32>) -> f32 {
  let lightDirection = normalize(positionWorldspace - spotLight.position);
  let coneFactor = smoothstep(
    spotLight.coneCos.y,
    spotLight.coneCos.x,
    dot(normalize(spotLight.direction), lightDirection)
  );
  let distanceAttenuation = getPointLightAttenuation(
    PointLight(spotLight.color, spotLight.position, spotLight.attenuation),
    distance(spotLight.position, positionWorldspace)
  );
  return distanceAttenuation / max(coneFactor, 0.0001);
}
`;var h=e(8780);function f(t={},i){let{color:e=[0,0,0],intensity:o=1}=t;return(0,h.d7)(e,(0,h.rY)(i,!0)).map(t=>t*o)}function v(){return{enabled:1,directionalLightCount:0,pointLightCount:0,spotLightCount:0,ambientColor:[.1,.1,.1],lights:m()}}function m(){return Array.from({length:5},()=>({color:[1,1,1],position:[1,1,2],direction:[1,1,1],attenuation:[1,0,0],coneCos:[1,0]}))}let _={name:"phongMaterial",firstBindingSlot:0,bindingLayout:[{name:"phongMaterial",group:3}],dependencies:[{props:{},uniforms:{},name:"lighting",defines:{},uniformTypes:{enabled:"i32",directionalLightCount:"i32",pointLightCount:"i32",spotLightCount:"i32",ambientColor:"vec3<f32>",lights:[{color:"vec3<f32>",position:"vec3<f32>",direction:"vec3<f32>",attenuation:"vec3<f32>",coneCos:"vec2<f32>"},5]},defaultUniforms:v(),bindingLayout:[{name:"lighting",group:2}],firstBindingSlot:0,source:u,vs:d,fs:d,getUniforms:function(t,i={}){if(!(t=t?{...t}:t))return v();t.lights&&(t={...t,...function(t){let i={pointLights:[],spotLights:[],directionalLights:[]};for(let e of t||[])switch(e.type){case"ambient":i.ambientLight=e;break;case"directional":i.directionalLights?.push(e);break;case"point":i.pointLights?.push(e);break;case"spot":i.spotLights?.push(e)}return i}(t.lights),lights:void 0});let{useByteColors:e,ambientLight:o,pointLights:n,spotLights:r,directionalLights:s}=t||{};if(!(o||n&&n.length>0||r&&r.length>0||s&&s.length>0))return{...v(),enabled:0};let l={...v(),...function({useByteColors:t,ambientLight:i,pointLights:e=[],spotLights:o=[],directionalLights:n=[]}){let r=m(),s=0,l=0,a=0,c=0;for(let i of e){if(s>=5)break;r[s]={...r[s],color:f(i,t),position:i.position,attenuation:i.attenuation||[1,0,0]},s++,l++}for(let i of o){if(s>=5)break;r[s]={...r[s],color:f(i,t),position:i.position,direction:i.direction,attenuation:i.attenuation||[1,0,0],coneCos:[Math.cos(i.innerConeAngle??0),Math.cos(i.outerConeAngle??Math.PI/4)]},s++,a++}for(let i of n){if(s>=5)break;r[s]={...r[s],color:f(i,t),direction:i.direction},s++,c++}return e.length+o.length+n.length>5&&p.c.warn("MAX_LIGHTS exceeded, truncating to 5")(),{ambientColor:f(i,t),directionalLightCount:c,pointLightCount:l,spotLightCount:a,lights:r}}({useByteColors:e,ambientLight:o,pointLights:n,spotLights:r,directionalLights:s})};return void 0!==t.enabled&&(l.enabled=t.enabled?1:0),l}},{name:"floatColors",props:{},uniforms:{},vs:l,fs:l,source:a,uniformTypes:{useByteColors:"f32"},defaultUniforms:{useByteColors:!0}}],source:`\
struct phongMaterialUniforms {
  unlit: u32,
  ambient: f32,
  diffuse: f32,
  shininess: f32,
  specularColor: vec3<f32>,
};

@group(3) @binding(auto) var<uniform> phongMaterial : phongMaterialUniforms;

fn lighting_getLightColor(surfaceColor: vec3<f32>, light_direction: vec3<f32>, view_direction: vec3<f32>, normal_worldspace: vec3<f32>, color: vec3<f32>) -> vec3<f32> {
  let halfway_direction: vec3<f32> = normalize(light_direction + view_direction);
  var lambertian: f32 = dot(light_direction, normal_worldspace);
  var specular: f32 = 0.0;
  if (lambertian > 0.0) {
    let specular_angle = max(dot(normal_worldspace, halfway_direction), 0.0);
    specular = pow(specular_angle, phongMaterial.shininess);
  }
  lambertian = max(lambertian, 0.0);
  return (
    lambertian * phongMaterial.diffuse * surfaceColor +
    specular * floatColors_normalize(phongMaterial.specularColor)
  ) * color;
}

fn lighting_getLightColor2(surfaceColor: vec3<f32>, cameraPosition: vec3<f32>, position_worldspace: vec3<f32>, normal_worldspace: vec3<f32>) -> vec3<f32> {
  var lightColor: vec3<f32> = surfaceColor;

  if (phongMaterial.unlit != 0u) {
    return surfaceColor;
  }

  if (lighting.enabled == 0) {
    return lightColor;
  }

  let view_direction: vec3<f32> = normalize(cameraPosition - position_worldspace);
  lightColor = phongMaterial.ambient * surfaceColor * lighting.ambientColor;

  for (var i: i32 = 0; i < lighting.pointLightCount; i++) {
    let pointLight: PointLight = lighting_getPointLight(i);
    let light_position_worldspace: vec3<f32> = pointLight.position;
    let light_direction: vec3<f32> = normalize(light_position_worldspace - position_worldspace);
    let light_attenuation = getPointLightAttenuation(
      pointLight,
      distance(light_position_worldspace, position_worldspace)
    );
    lightColor += lighting_getLightColor(
      surfaceColor,
      light_direction,
      view_direction,
      normal_worldspace,
      pointLight.color / light_attenuation
    );
  }

  for (var i: i32 = 0; i < lighting.spotLightCount; i++) {
    let spotLight: SpotLight = lighting_getSpotLight(i);
    let light_position_worldspace: vec3<f32> = spotLight.position;
    let light_direction: vec3<f32> = normalize(light_position_worldspace - position_worldspace);
    let light_attenuation = getSpotLightAttenuation(spotLight, position_worldspace);
    lightColor += lighting_getLightColor(
      surfaceColor,
      light_direction,
      view_direction,
      normal_worldspace,
      spotLight.color / light_attenuation
    );
  }

  for (var i: i32 = 0; i < lighting.directionalLightCount; i++) {
    let directionalLight: DirectionalLight = lighting_getDirectionalLight(i);
    lightColor += lighting_getLightColor(surfaceColor, -directionalLight.direction, view_direction, normal_worldspace, directionalLight.color);
  }  
  
  return lightColor;
}

fn lighting_getSpecularLightColor(cameraPosition: vec3<f32>, position_worldspace: vec3<f32>, normal_worldspace: vec3<f32>) -> vec3<f32>{
  var lightColor = vec3<f32>(0, 0, 0);
  let surfaceColor = vec3<f32>(0, 0, 0);

  if (lighting.enabled != 0) {
    let view_direction = normalize(cameraPosition - position_worldspace);

    for (var i: i32 = 0; i < lighting.pointLightCount; i++) {
      let pointLight: PointLight = lighting_getPointLight(i);
      let light_position_worldspace: vec3<f32> = pointLight.position;
      let light_direction: vec3<f32> = normalize(light_position_worldspace - position_worldspace);
      let light_attenuation = getPointLightAttenuation(
        pointLight,
        distance(light_position_worldspace, position_worldspace)
      );
      lightColor += lighting_getLightColor(
        surfaceColor,
        light_direction,
        view_direction,
        normal_worldspace,
        pointLight.color / light_attenuation
      );
    }

    for (var i: i32 = 0; i < lighting.spotLightCount; i++) {
      let spotLight: SpotLight = lighting_getSpotLight(i);
      let light_position_worldspace: vec3<f32> = spotLight.position;
      let light_direction: vec3<f32> = normalize(light_position_worldspace - position_worldspace);
      let light_attenuation = getSpotLightAttenuation(spotLight, position_worldspace);
      lightColor += lighting_getLightColor(
        surfaceColor,
        light_direction,
        view_direction,
        normal_worldspace,
        spotLight.color / light_attenuation
      );
    }

    for (var i: i32 = 0; i < lighting.directionalLightCount; i++) {
        let directionalLight: DirectionalLight = lighting_getDirectionalLight(i);
        lightColor += lighting_getLightColor(surfaceColor, -directionalLight.direction, view_direction, normal_worldspace, directionalLight.color);
    }
  }
  return lightColor;
}
`,vs:`\
layout(std140) uniform phongMaterialUniforms {
  uniform bool unlit;
  uniform float ambient;
  uniform float diffuse;
  uniform float shininess;
  uniform vec3  specularColor;
} material;
`,fs:`\
layout(std140) uniform phongMaterialUniforms {
  uniform bool unlit;
  uniform float ambient;
  uniform float diffuse;
  uniform float shininess;
  uniform vec3  specularColor;
} material;

vec3 lighting_getLightColor(vec3 surfaceColor, vec3 light_direction, vec3 view_direction, vec3 normal_worldspace, vec3 color) {
  vec3 halfway_direction = normalize(light_direction + view_direction);
  float lambertian = dot(light_direction, normal_worldspace);
  float specular = 0.0;
  if (lambertian > 0.0) {
    float specular_angle = max(dot(normal_worldspace, halfway_direction), 0.0);
    specular = pow(specular_angle, material.shininess);
  }
  lambertian = max(lambertian, 0.0);
  return (lambertian * material.diffuse * surfaceColor + specular * floatColors_normalize(material.specularColor)) * color;
}

vec3 lighting_getLightColor(vec3 surfaceColor, vec3 cameraPosition, vec3 position_worldspace, vec3 normal_worldspace) {
  vec3 lightColor = surfaceColor;

  if (material.unlit) {
    return surfaceColor;
  }

  if (lighting.enabled == 0) {
    return lightColor;
  }

  vec3 view_direction = normalize(cameraPosition - position_worldspace);
  lightColor = material.ambient * surfaceColor * lighting.ambientColor;

  for (int i = 0; i < lighting.pointLightCount; i++) {
    PointLight pointLight = lighting_getPointLight(i);
    vec3 light_position_worldspace = pointLight.position;
    vec3 light_direction = normalize(light_position_worldspace - position_worldspace);
    float light_attenuation = getPointLightAttenuation(pointLight, distance(light_position_worldspace, position_worldspace));
    lightColor += lighting_getLightColor(surfaceColor, light_direction, view_direction, normal_worldspace, pointLight.color / light_attenuation);
  }

  for (int i = 0; i < lighting.spotLightCount; i++) {
    SpotLight spotLight = lighting_getSpotLight(i);
    vec3 light_position_worldspace = spotLight.position;
    vec3 light_direction = normalize(light_position_worldspace - position_worldspace);
    float light_attenuation = getSpotLightAttenuation(spotLight, position_worldspace);
    lightColor += lighting_getLightColor(surfaceColor, light_direction, view_direction, normal_worldspace, spotLight.color / light_attenuation);
  }

  for (int i = 0; i < lighting.directionalLightCount; i++) {
    DirectionalLight directionalLight = lighting_getDirectionalLight(i);
    lightColor += lighting_getLightColor(surfaceColor, -directionalLight.direction, view_direction, normal_worldspace, directionalLight.color);
  }
  
  return lightColor;
}
`,defines:{LIGHTING_FRAGMENT:!0},uniformTypes:{unlit:"i32",ambient:"f32",diffuse:"f32",shininess:"f32",specularColor:"vec3<f32>"},defaultUniforms:{unlit:!1,ambient:.35,diffuse:.6,shininess:32,specularColor:[38.25,38.25,38.25]},getUniforms:t=>({..._.defaultUniforms,...t})};var C=e(5022),y=e(3609),x=e(9335),L=e(3746),P=e(4637);let w=Math.PI/180,b=new Float32Array(16),S=new Float32Array(12);function M(t,i,e){let o=i[0]*w,n=i[1]*w,r=i[2]*w,s=Math.sin(r),l=Math.sin(o),a=Math.sin(n),c=Math.cos(r),g=Math.cos(o),p=Math.cos(n),d=e[0],u=e[1],h=e[2];t[0]=d*p*g,t[1]=d*a*g,t[2]=-(d*l),t[3]=u*(-a*c+p*l*s),t[4]=u*(p*c+a*l*s),t[5]=u*g*s,t[6]=h*(a*s+p*l*c),t[7]=h*(-p*s+a*l*c),t[8]=h*g*c}function A(t){return t[0]=t[0],t[1]=t[1],t[2]=t[2],t[3]=t[4],t[4]=t[5],t[5]=t[6],t[6]=t[8],t[7]=t[9],t[8]=t[10],t[9]=t[12],t[10]=t[13],t[11]=t[14],t.subarray(0,12)}let I={size:12,accessor:["getOrientation","getScale","getTranslation","getTransformMatrix"],shaderAttributes:{instanceModelMatrixCol0:{size:3,elementOffset:0},instanceModelMatrixCol1:{size:3,elementOffset:3},instanceModelMatrixCol2:{size:3,elementOffset:6},instanceTranslation:{size:3,elementOffset:9}},update(t,{startRow:i,endRow:e}){let{data:o,getOrientation:n,getScale:r,getTranslation:s,getTransformMatrix:l}=this.props,a=Array.isArray(l),c=a&&16===l.length,g=Array.isArray(r),p=Array.isArray(n),d=Array.isArray(s),u=c||!a&&!!l(o[0]);u?t.constant=c:t.constant=p&&g&&d;let h=t.value;if(t.constant){let i;u?(b.set(l),i=A(b)):(M(i=S,n,r),i.set(s,9)),t.value=new Float32Array(i)}else{let a=i*t.size,{iterable:f,objectInfo:v}=(0,P.jB)(o,i,e);for(let t of f){let i;(v.index++,u)?(b.set(c?l:l(t,v)),i=A(b)):(M(i=S,p?n:n(t,v),g?r:r(t,v)),i.set(d?s:s(t,v),9)),h[a++]=i[0],h[a++]=i[1],h[a++]=i[2],h[a++]=i[3],h[a++]=i[4],h[a++]=i[5],h[a++]=i[6],h[a++]=i[7],h[a++]=i[8],h[a++]=i[9],h[a++]=i[10],h[a++]=i[11]}}}},T=`\
layout(std140) uniform simpleMeshUniforms {
  float sizeScale;
  bool composeModelMatrix;
  bool hasTexture;
  bool flatShading;
} simpleMesh;
`,R={name:"simpleMesh",source:`\
struct SimpleMeshUniforms {
  sizeScale: f32,
  composeModelMatrix: f32,
  hasTexture: f32,
  flatShading: f32,
};

@group(0) @binding(auto) var<uniform> simpleMesh: SimpleMeshUniforms;
@group(0) @binding(auto) var simpleMeshTexture: texture_2d<f32>;
@group(0) @binding(auto) var simpleMeshTextureSampler: sampler;
`,vs:T,fs:T,uniformTypes:{sizeScale:"f32",composeModelMatrix:"f32",hasTexture:"f32",flatShading:"f32"}};var E=`#version 300 es
#define SHADER_NAME simple-mesh-layer-vs
in vec3 positions;
in vec3 normals;
in vec3 colors;
in vec2 texCoords;
in vec3 instancePositions;
in vec3 instancePositions64Low;
in vec4 instanceColors;
in vec3 instanceModelMatrixCol0;
in vec3 instanceModelMatrixCol1;
in vec3 instanceModelMatrixCol2;
in vec3 instanceTranslation;
out vec2 vTexCoord;
out vec3 cameraPosition;
out vec3 normals_commonspace;
out vec4 position_commonspace;
out vec4 vColor;
void main(void) {
geometry.worldPosition = instancePositions;
geometry.uv = texCoords;
geometry.pickingColor = picking_getPickingColorFromInstanceID();
vTexCoord = texCoords;
cameraPosition = project.cameraPosition;
vColor = vec4(colors * instanceColors.rgb, instanceColors.a);
mat3 instanceModelMatrix = mat3(instanceModelMatrixCol0, instanceModelMatrixCol1, instanceModelMatrixCol2);
vec3 pos = (instanceModelMatrix * positions) * simpleMesh.sizeScale + instanceTranslation;
if (simpleMesh.composeModelMatrix) {
DECKGL_FILTER_SIZE(pos, geometry);
normals_commonspace = project_normal(instanceModelMatrix * normals);
geometry.worldPosition += pos;
gl_Position = project_position_to_clipspace(pos + instancePositions, instancePositions64Low, vec3(0.0), position_commonspace);
geometry.position = position_commonspace;
}
else {
pos = project_size(pos);
DECKGL_FILTER_SIZE(pos, geometry);
gl_Position = project_position_to_clipspace(instancePositions, instancePositions64Low, pos, position_commonspace);
geometry.position = position_commonspace;
normals_commonspace = project_normal(instanceModelMatrix * normals);
}
geometry.normal = normals_commonspace;
DECKGL_FILTER_GL_POSITION(gl_Position, geometry);
DECKGL_FILTER_COLOR(vColor, geometry);
}
`,O=`#version 300 es
#define SHADER_NAME simple-mesh-layer-fs
precision highp float;
uniform sampler2D sampler;
in vec2 vTexCoord;
in vec3 cameraPosition;
in vec3 normals_commonspace;
in vec4 position_commonspace;
in vec4 vColor;
out vec4 fragColor;
void main(void) {
geometry.uv = vTexCoord;
vec3 normal;
if (simpleMesh.flatShading) {
normal = normalize(cross(dFdx(position_commonspace.xyz), dFdy(position_commonspace.xyz)));
} else {
normal = normals_commonspace;
}
vec4 color = simpleMesh.hasTexture ? texture(sampler, vTexCoord) : vColor;
DECKGL_FILTER_COLOR(color, geometry);
vec3 lightColor = lighting_getLightColor(color.rgb, cameraPosition, position_commonspace.xyz, normal);
fragColor = vec4(lightColor, color.a * layer.opacity);
}
`,z=`\
struct Attributes {
  @builtin(instance_index) instanceIndex: u32,
  @location(0) positions: vec3<f32>,
  @location(1) normals: vec3<f32>,
  @location(2) colors: vec3<f32>,
  @location(3) texCoords: vec2<f32>,
  @location(4) instancePositions: vec3<f32>,
  @location(5) instancePositions64Low: vec3<f32>,
  @location(6) instanceColors: vec4<f32>,
  @location(7) instanceModelMatrixCol0: vec3<f32>,
  @location(8) instanceModelMatrixCol1: vec3<f32>,
  @location(9) instanceModelMatrixCol2: vec3<f32>,
  @location(10) instanceTranslation: vec3<f32>,
};

struct Varyings {
  @builtin(position) position: vec4<f32>,
  @location(0) color: vec4<f32>,
  @location(1) texCoords: vec2<f32>,
  @location(2) normal: vec3<f32>,
  @location(3) positionCommon: vec3<f32>,
  @location(4) pickingColor: vec3<f32>,
};

@vertex
fn vertexMain(attributes: Attributes) -> Varyings {
  var varyings: Varyings;

  geometry.worldPosition = attributes.instancePositions;
  geometry.uv = attributes.texCoords;
  geometry.pickingColor = picking_getPickingColorFromIndex(attributes.instanceIndex);

  let instanceModelMatrix = mat3x3<f32>(
    attributes.instanceModelMatrixCol0,
    attributes.instanceModelMatrixCol1,
    attributes.instanceModelMatrixCol2
  );
  let meshPosition =
    (instanceModelMatrix * attributes.positions) * simpleMesh.sizeScale +
    attributes.instanceTranslation;

  if (simpleMesh.composeModelMatrix > 0.5) {
    geometry.normal = project_normal(instanceModelMatrix * attributes.normals);
    geometry.worldPosition += meshPosition;
    let projected = project_position_to_clipspace_and_commonspace(
      attributes.instancePositions + meshPosition,
      attributes.instancePositions64Low,
      vec3<f32>(0.0)
    );
    geometry.position = projected.commonPosition;
    varyings.position = projected.clipPosition;
  } else {
    let projected = project_position_to_clipspace_and_commonspace(
      attributes.instancePositions,
      attributes.instancePositions64Low,
      project_size_vec3(meshPosition)
    );
    geometry.position = projected.commonPosition;
    geometry.normal = project_normal(instanceModelMatrix * attributes.normals);
    varyings.position = projected.clipPosition;
  }

  varyings.color = vec4<f32>(
    attributes.colors * attributes.instanceColors.rgb,
    attributes.instanceColors.a
  );
  varyings.texCoords = attributes.texCoords;
  varyings.normal = geometry.normal;
  varyings.positionCommon = geometry.position.xyz;
  varyings.pickingColor = geometry.pickingColor;
  return varyings;
}

@fragment
fn fragmentMain(varyings: Varyings) -> @location(0) vec4<f32> {
  geometry.uv = varyings.texCoords;

  if (picking.isActive > 0.5) {
    if (!picking_isColorValid(varyings.pickingColor)) {
      discard;
    }
    return vec4<f32>(varyings.pickingColor, 1.0);
  }

  var color = varyings.color;
  if (simpleMesh.hasTexture > 0.5) {
    color = textureSample(simpleMeshTexture, simpleMeshTextureSampler, varyings.texCoords);
  }

  var normal = varyings.normal;
  if (simpleMesh.flatShading > 0.5) {
    // WebGPU's screen-space Y axis reverses the derivative orientation used by GLSL flat shading.
    normal = normalize(cross(dpdy(varyings.positionCommon), dpdx(varyings.positionCommon)));
  }

  color = vec4<f32>(
    lighting_getLightColor2(color.rgb, project.cameraPosition, varyings.positionCommon, normal),
    color.a * layer.opacity
  );

  if (picking.isHighlightActive > 0.5) {
    let highlightedColor = picking_normalizeColor(picking.highlightedObjectColor);
    if (picking_isColorZero(abs(varyings.pickingColor - highlightedColor))) {
      let blendedAlpha = picking.highlightColor.a + color.a * (1.0 - picking.highlightColor.a);
      if (blendedAlpha > 0.0) {
        color = vec4<f32>(
          mix(color.rgb, picking.highlightColor.rgb, picking.highlightColor.a / blendedAlpha),
          blendedAlpha
        );
      }
    }
  }

  return deckgl_premultiplied_alpha(color);
}
`;function k(t){let i=t.positions||t.POSITION;o.Z.assert(i,'no "postions" or "POSITION" attribute in mesh');let e=i.value.length/i.size,n=t.COLOR_0||t.colors;n||(n={size:3,value:new Float32Array(3*e).fill(1)});let r=t.NORMAL||t.normals;r||(r={size:3,value:new Float32Array(3*e).fill(0)});let s=t.TEXCOORD_0||t.texCoords;return s||(s={size:2,value:new Float32Array(2*e).fill(0)}),{positions:i,colors:n,normals:r,texCoords:s}}function F(t){return t instanceof x.Z?(t.attributes=k(t.attributes),t):new x.Z(t.attributes?{...t,topology:"triangle-list",attributes:k(t.attributes)}:{topology:"triangle-list",attributes:k(t)})}class G extends n.Z{getShaders(){return super.getShaders({vs:E,fs:O,source:z,modules:[r.Z,s.Z,_,C.ZP,R]})}getBounds(){if(this.props._instanced)return super.getBounds();let t=this.state.positionBounds;if(t)return t;let{mesh:i}=this.props;if(!i)return null;if(!(t=i.header?.boundingBox)){let{attributes:e}=F(i);e.POSITION=e.POSITION||e.positions,t=function(t){let i=1/0,e=1/0,o=1/0,n=-1/0,r=-1/0,s=-1/0,l=t.POSITION?t.POSITION.value:[],a=l&&l.length;for(let t=0;t<a;t+=3){let a=l[t],c=l[t+1],g=l[t+2];i=a<i?a:i,e=c<e?c:e,o=g<o?g:o,n=a>n?a:n,r=c>r?c:r,s=g>s?g:s}return[[i,e,o],[n,r,s]]}(e)}return this.state.positionBounds=t,t}initializeState(){this.getAttributeManager().addInstanced({instancePositions:{transition:!0,type:"float64",fp64:this.use64bitPositions(),size:3,accessor:"getPosition"},instanceColors:{type:"unorm8",transition:!0,size:this.props.colorFormat.length,accessor:"getColor",defaultValue:[0,0,0,255]},instanceModelMatrix:I}),this.setState({emptyTexture:this.context.device.createTexture({data:new Uint8Array(4),width:1,height:1})})}updateState(t){super.updateState(t);let{props:i,oldProps:e,changeFlags:o}=t;if(i.mesh!==e.mesh||o.extensionsChanged){if(this.state.positionBounds=null,this.state.model?.destroy(),i.mesh){this.state.model=this.getModel(i.mesh);let t=i.mesh.attributes||i.mesh;this.setState({hasNormals:!!(t.NORMAL||t.normals)})}this.getAttributeManager().invalidateAll()}i.texture!==e.texture&&i.texture instanceof y.x&&this.setTexture(i.texture),this.state.model&&this.state.model.setTopology(this.props.wireframe?"line-strip":"triangle-list")}finalizeState(t){super.finalizeState(t),this.state.emptyTexture.delete()}draw({uniforms:t}){let{model:i}=this.state;if(!i)return;let{viewport:e,renderPass:o}=this.context,{sizeScale:n,coordinateSystem:r,_instanced:s}=this.props,l={sizeScale:n,composeModelMatrix:!s||"cartesian"===r||"meter-offsets"===r||"default"===r&&!e.isGeospatial,flatShading:!this.state.hasNormals};i.shaderInputs.setProps({simpleMesh:l}),i.draw(o)}get isLoaded(){return!!(this.state?.model&&super.isLoaded)}getModel(t){let i=new L.H(this.context.device,{...this.getShaders(),id:this.props.id,bufferLayout:this.getAttributeManager().getBufferLayouts(),geometry:F(t),isInstanced:!0});return i.shaderInputs.setProps({simpleMesh:this.getTextureProps(this.props.texture)}),i}setTexture(t){let{model:i}=this.state;i&&i.shaderInputs.setProps({simpleMesh:this.getTextureProps(t)})}getTextureProps(t){let i=t||this.state.emptyTexture;return{..."webgpu"===this.context.device.type?{simpleMeshTexture:i}:{sampler:i},hasTexture:!!t}}}G.defaultProps={mesh:{type:"object",value:null,async:!0},texture:{type:"image",value:null,async:!0},sizeScale:{type:"number",value:1,min:0},_instanced:!0,wireframe:!1,material:!0,getPosition:{type:"accessor",value:t=>t.position},getColor:{type:"accessor",value:[0,0,0,255]},getOrientation:{type:"accessor",value:[0,0,0]},getScale:{type:"accessor",value:[1,1,1]},getTranslation:{type:"accessor",value:[0,0,0]},getTransformMatrix:{type:"accessor",value:[]},textureParameters:{type:"object",ignore:!0,value:null}},G.layerName="SimpleMeshLayer";var U=G},7299:function(t,i,e){e.d(i,{f:function(){return l}});var o=e(9335),n=e(1409);let r={x:[2,0,1],y:[0,1,2],z:[1,2,0]};class s extends o.Z{constructor(t={}){let{id:i=(0,n.h)("truncated-code-geometry")}=t,{indices:e,attributes:o}=function(t={}){let{bottomRadius:i=0,topRadius:e=0,height:o=1,nradial:n=10,nvertical:s=10,verticalAxis:l="y",topCap:a=!1,bottomCap:c=!1}=t,g=(a?2:0)+(c?2:0),p=(n+1)*(s+1+g),d=Math.atan2(i-e,o),u=Math.sin,h=Math.cos,f=Math.PI,v=h(d),m=u(d),_=a?-2:0,C=s+(c?2:0),y=n+1,x=new Uint16Array(n*(s+g)*6),L=r[l],P=new Float32Array(3*p),w=new Float32Array(3*p),b=new Float32Array(2*p),S=0,M=0;for(let t=_;t<=C;t++){let r,l=t/s,a=o*l;t<0?(a=0,l=1,r=i):t>s?(a=o,l=1,r=e):r=i+t/s*(e-i),(-2===t||t===s+2)&&(r=0,l=0),a-=o/2;for(let i=0;i<y;i++){let e=u(i*f*2/n),o=h(i*f*2/n);P[S+L[0]]=e*r,P[S+L[1]]=a,P[S+L[2]]=o*r,w[S+L[0]]=t<0||t>s?0:e*v,w[S+L[1]]=t<0?-1:t>s?1:m,w[S+L[2]]=t<0||t>s?0:o*v,b[M+0]=i/n,b[M+1]=l,M+=2,S+=3}}for(let t=0;t<s+g;t++)for(let i=0;i<n;i++){let e=(t*n+i)*6;x[e+0]=y*(t+0)+0+i,x[e+1]=y*(t+0)+1+i,x[e+2]=y*(t+1)+1+i,x[e+3]=y*(t+0)+0+i,x[e+4]=y*(t+1)+1+i,x[e+5]=y*(t+1)+0+i}return{indices:x,attributes:{POSITION:P,NORMAL:w,TEXCOORD_0:b}}}(t);super({...t,id:i,topology:"triangle-list",indices:e,attributes:{POSITION:{size:3,value:o.POSITION},NORMAL:{size:3,value:o.NORMAL},TEXCOORD_0:{size:2,value:o.TEXCOORD_0},...t.attributes}})}}class l extends s{constructor(t={}){let{id:i=(0,n.h)("cylinder-geometry"),radius:e=1}=t;super({...t,id:i,bottomRadius:e,topRadius:e})}}}}]);