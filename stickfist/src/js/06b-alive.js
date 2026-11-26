/* ============================================================================
   6b. ALIVE. A good card's picture moves, and each one moves in its own way.
   This is not an effect laid over the cards. Every rare card or better has its own little scene, written for its own
   picture: the tornado twists and its lightning flashes; the great wave's foam pours off its lip; the angel's wings beat;
   the kraken's arms sway over rippling water; the eclipse's rays turn; the rocket's plume pours down and the pad shakes;
   the suit swings on its hanger; the flag waves; the black hole's disc turns and the tape slips. The picture itself is what
   moves: it is drawn through a shader that bends, flows, turns and lights parts of it.
   A scene is a short list of moves, each tied to a place in the picture (a centre and a size, as fractions of the picture):
     SW turn      a region turns about its centre (discs, storm tops)
     FL flow      a region streams one way without ever running out (plumes, smoke, clouds, foam)
     WV wave      ripples and sways (water, cloth, arms, grass)
     PU pulse     a region breathes in and out and glows (coronas, lamps, a chest)
     RY rays      light turning about a point (sun shafts, a corona)
     GL glitch    bands of the picture slip sideways for an instant (tape, screens)
     TW twinkle   small cells brighten and dim out of step (stars, lights, grain)
     FP flap      a region beats about its middle line (wings)
     BO bob       a region drifts or shudders (a floating figure, a rocket on its plume)
     HZ haze      a slow boil (heat, mist, deep water)
     FK flicker   sudden light, now and then (lightning, flame)
     RK rock      a region swings about a pivot (a hanging suit, a tumbling figure)
   It runs on a card shown large (the one just turned over, and the card window), not on lists, and not with reduced
   motion. Without WebGL the picture simply stays still.
   ========================================================================== */
const Alive = (() => {
  const SW = 1, FL = 2, WV = 3, PU = 4, RY = 5, GL = 6, TW = 7, FP = 8, BO = 9, HZ = 10, FK = 11, RK = 12;
  // each move: [kind, centre x, centre y, half-width, half-height, then up to four numbers that set it]
  const SCENES = {
    // First Print
    tempest:   [[SW, .5, .2, .48, .2, .28], [WV, .5, .62, .2, .42, .010, 0, 16, 3.2], [FK, .5, .5, .6, .6, .55, 7, .82], [HZ, .5, .2, .5, .22, .006, 6, .5], [TW, .5, .5, .6, .6, .18, 5, .02]],                      // the funnel's top turns, the column twists, lightning
    surge:     [[FL, .68, .26, .3, .24, -.035, .03], [WV, .5, .86, .6, .16, .008, 0, 34, 2.6], [PU, .5, .6, .7, .6, .008, .8, .06], [HZ, .62, .3, .34, .26, .006, 9, .9], [TW, .7, .25, .3, .25, .15, 6, .015]],            // foam pours off the lip; the sea under it rolls
    phantom:   [[FP, .5, .3, .52, .26, .11, 1.5, .022], [BO, .5, .62, .2, .2, 0, .004, 1.5], [TW, .5, .4, .6, .5, .22, 3, .02], [PU, .5, .33, .3, .3, 0, 1.5, .1]],                                                     // the wings beat
    kraken:    [[WV, .5, .4, .6, .38, .011, 0, 8, 1.4], [WV, .5, .9, .6, .14, .006, 0, 60, 3], [PU, .5, .8, .09, .07, 0, 7, .35], [BO, .5, .84, .1, .06, 0, .004, 1.6], [TW, .4, .45, .5, .4, .2, 2.2, .03]],            // the arms sway, the water ripples, the boat's lamp gutters
    colossus:  [[PU, .5, .48, .6, .55, .007, .6, .07], [RY, .5, -.05, .7, .7, .16, 7, .25], [TW, .5, .5, .7, .7, .22, 4, .008], [HZ, .5, .85, .6, .2, .003, 10, .6]],                                                   // the face breathes under moving light; the sand shimmers
    leviathan: [[BO, .55, .38, .5, .34, .004, .012, .7], [WV, .55, .38, .5, .3, 0, .007, 7, 1.2], [HZ, .5, .5, .7, .7, .004, 5, .35], [TW, .5, .5, .7, .7, .12, 2.5, .03]],                                           // the whale swims through the cloud
    null:      [[PU, .5, .42, .46, .4, .028, 1.1, .22], [RY, .5, .42, .5, .45, .2, 4, .5], [WV, .5, .8, .25, .22, .007, 0, 11, 1.3], [TW, .5, .42, .5, .45, .2, 5, .015]],                                              // the star pulses about its eye
    shogun:    [[RY, .5, .45, .75, .6, .2, 9, .3], [PU, .5, .4, .7, .5, .006, .7, .1], [WV, .5, .93, .6, .08, .005, 0, 45, 2], [HZ, .5, .35, .6, .4, .003, 7, .4], [TW, .5, .4, .7, .5, .1, 3, .012]],                   // shafts of light turn over the kneeling figure; the grass stirs
    ronin:     [[WV, .27, .36, .22, .07, 0, .013, 24, 4.5], [FK, .8, .3, .3, .4, .6, 6, .84], [TW, .5, .5, .75, .75, .22, 9, .012], [HZ, .8, .4, .25, .4, .005, 8, .8], [BO, .49, .5, .08, .2, .002, 0, 1.3]],            // the scarf streams, the storm flashes, the rain falls
    titan:     [[PU, .5, .5, .6, .6, .008, .55, .08], [TW, .5, .5, .7, .7, .35, 3.5, .01], [BO, .45, .72, .26, .18, .004, .007, .8], [HZ, .5, .5, .6, .6, .0035, 9, .5], [RY, .5, .05, .6, .6, .14, 5, .2]],              // the statue's hand moves; dust hangs in the light
    grimm:     [[GL, .5, .5, .8, .8, .035, 36, 8], [HZ, .5, .3, .16, .36, .006, 9, 1.2], [PU, .5, .6, .2, .12, 0, 2.2, .25], [WV, .5, .9, .6, .14, .007, 0, 50, 3], [TW, .5, .3, .2, .35, .2, 6, .02]],                   // the tape slips; the book glows
    reaper:    [[FL, .5, .24, .62, .27, .014, 0], [WV, .5, .82, .62, .2, .008, 0, 70, 2.5], [PU, .5, .6, .62, .07, 0, 1.1, .22], [HZ, .5, .25, .6, .26, .004, 5, .4], [RK, .56, .66, .1, .14, .02, 1]],                   // the burning sky drifts; its reflection ripples
    umbra:     [[RY, .5, .36, .75, .6, .24, 14, .35], [PU, .5, .36, .55, .45, .012, .9, .16], [TW, .5, .6, .75, .6, .3, 4, .012], [HZ, .5, .36, .55, .45, .004, 8, .6]],                                                // the corona's rays turn and flare
    // Moonshot
    ignition:  [[FL, .24, .86, .3, .16, -.03, -.012, 0, .004], [FL, .76, .86, .3, .16, .03, -.012, 0, .004], [HZ, .5, .86, .6, .16, .008, 9, 1.6], [FK, .5, .85, .6, .17, .2, 14, .5], [BO, .5, .38, .14, .4, .0018, .0012, 41, 1]],   // fire rolls out both ways; the rocket shudders
    console:   [[TW, .5, .5, .8, .8, .45, 2.6, .035], [GL, .5, .5, .8, .8, .006, 60, 6], [WV, .13, .34, .1, .06, 0, .012, 70, 7], [PU, .5, .33, .3, .14, 0, 2, .14], [BO, .5, .6, .12, .1, 0, .003, 1.4]],                 // lights blink, a trace runs, the screens flicker
    suit:      [[RK, .72, .55, .26, .45, .045, 1.1, 0, -.3], [BO, .3, .18, .22, .16, 0, .007, 1.3], [TW, .5, .5, .8, .8, .1, 3, .02]],                                                                                  // the suit swings on its hanger; the helmet is lifted
    gantry:    [[TW, .72, .5, .14, .48, .5, 3, .022], [FL, .4, .82, .3, .12, 0, -.02, 0, .003], [HZ, .4, .82, .34, .14, .006, 8, 1], [PU, .4, .4, .1, .4, 0, 3, .06], [TW, .4, .85, .5, .12, .3, 5, .02]],                // the tower's lights blink; steam rises off the pad
    liftoff:   [[FL, .5, .55, .17, .24, 0, .045, 0, .004], [HZ, .5, .85, .52, .17, .012, 5, .7], [PU, .5, .88, .55, .18, .012, .9, .05], [BO, .5, .2, .12, .2, .0022, .0015, 37, 1], [FK, .5, .4, .15, .12, .25, 16, .45]],  // the plume pours down, the cloud billows, the rocket shakes
    booster:   [[FL, .5, .72, .1, .3, 0, .05, 0, .004], [FL, .18, .75, .11, .26, -.008, .045, 0, .004], [FL, .82, .75, .11, .26, .008, .045, 0, .004], [RK, .32, .4, .1, .14, .05, .8], [RK, .68, .4, .1, .14, -.05, .8], [BO, .5, .25, .08, .25, .002, .001, 39, 1]],   // three plumes; the boosters peel away
    apogee:    [[RK, .45, .5, .28, .32, .09, .5], [BO, .45, .5, .28, .32, .006, .014, .7], [FL, .5, .92, .62, .13, .02, 0], [RY, .86, .07, .32, .26, .3, 10, .6], [TW, .3, .3, .5, .4, .5, 2, .02], [BO, .9, .55, .14, .12, .004, 0, .5, 1]],   // the figure tumbles, weightless; the Earth turns below; the sun flares
    luna:      [[WV, .83, .32, .13, .1, 0, .012, 30, 3.5], [FL, .3, .38, .3, .24, .012, 0], [TW, .5, .75, .6, .25, .2, 3, .02], [BO, .5, .45, .1, .2, 0, .003, 1.2], [HZ, .3, .38, .3, .24, .003, 6, .3]],                // the flag waves; the Earth turns behind
    mars:      [[FL, .5, .5, .22, .3, 0, .03, 0, .003], [HZ, .5, .5, .5, .5, .005, 7, .6], [TW, .5, .5, .75, .75, .35, 6, .01], [PU, .55, .1, .12, .1, 0, 1, .18]],                                                      // mist runs down the canyon; the dust never settles
    horizon:   [[SW, .5, .38, .5, .31, .26], [GL, .5, .5, .8, .8, .014, 28, 5], [PU, .5, .37, .5, .3, .006, 1.3, .14], [WV, .5, .92, .3, .1, .008, 0, 60, 3], [HZ, .5, .6, .4, .12, .004, 8, 1]],                        // the disc turns; the tape slips
  };
  const CHROMA = { grimm: .004, horizon: .0035, console: .002 };                              // on these the red of the picture rides a hair off the rest, as on a bad tape
  const VS = "attribute vec2 p;varying vec2 v;void main(){v=vec2(p.x*.5+.5,.5-p.y*.5);gl_Position=vec4(p,0.,1.);}";
  const FS = `precision mediump float;varying vec2 v;uniform sampler2D tex;uniform float t,asp,chroma;uniform vec4 crop;uniform vec4 uc[6];uniform vec4 up[6];uniform float uk[6];
float hash(vec2 q){return fract(sin(dot(q,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 q){vec2 i=floor(q),f=fract(q);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}
vec2 turn(vec2 o,vec2 c,float a){vec2 d=o-c;d.x*=asp;float s=sin(a),k=cos(a);d=vec2(d.x*k-d.y*s,d.x*s+d.y*k);d.x/=asp;return c+d;}
vec2 warp(vec2 uv,float ph,out float gain){vec2 o=uv;gain=1.;
 for(int i=0;i<6;i++){float ty=uk[i];if(ty<.5)continue;vec2 c=uc[i].xy,r=uc[i].zw;vec4 q=up[i];float m=1.-smoothstep(.7,1.,length((uv-c)/r));if(m<=0.)continue;
  if(ty<1.5){vec2 d=(o-c)/r;float an=q.x*ph*m,s=sin(an),k=cos(an);o=c+vec2(d.x*k-d.y*s,d.x*s+d.y*k)*r;}
  else if(ty<2.5){o-=q.xy*ph*m;o.x+=q.w*sin(uv.y*40.+t*6.)*m;}
  else if(ty<3.5){o+=vec2(q.x*sin(uv.y*q.z+t*q.w),q.y*sin(uv.x*q.z+t*q.w))*m;}
  else if(ty<4.5){o=c+(o-c)*(1.-q.x*sin(t*q.y)*m);gain+=q.z*(.5+.5*sin(t*q.y+q.w))*m;}
  else if(ty<5.5){vec2 d=uv-c;d.x*=asp;gain+=q.x*sin(atan(d.y,d.x)*q.y+t*q.z)*m;}
  else if(ty<6.5){float b=floor(uv.y*q.y),tk=floor(t*q.z);if(hash(vec2(b,tk))>.86)o.x+=(hash(vec2(tk,b))-.5)*2.*q.x*m;}
  else if(ty<7.5){gain+=q.x*sin(t*q.y+hash(floor(uv/q.z))*6.2832)*m;}
  else if(ty<8.5){float s=1.+q.x*sin(t*q.y)*m;o.x=c.x+(o.x-c.x)/s;o.y+=q.z*sin(t*q.y+1.2)*m*abs(uv.x-c.x)/r.x;}
  else if(ty<9.5){o-=vec2(q.x*sin(t*q.z),q.y*sin(t*q.z+q.w))*m;}
  else if(ty<10.5){o+=(vec2(noise(uv*q.y+t*q.z),noise(uv*q.y+7.3-t*q.z))-.5)*2.*q.x*m;}
  else if(ty<11.5){float tk=floor(t*q.y);gain+=q.x*step(q.z,hash(vec2(tk,3.7)))*(.6+.4*hash(vec2(tk,floor(t*30.))))*m;}
  else{o=turn(o,c+q.zw,q.x*sin(t*q.y)*m);}
 }return o;}
void main(){float T=3.2,a=fract(t/T),b=fract(t/T+.5),ga,gb;vec2 ua=warp(v,(a-.5)*T,ga),ub=warp(v,(b-.5)*T,gb);float w=1.-abs(2.*a-1.);
 vec3 ca=texture2D(tex,crop.xy+ua*crop.zw).rgb,cb=texture2D(tex,crop.xy+ub*crop.zw).rgb,col=mix(cb,ca,w);
 if(chroma>0.){float k=chroma*(.6+.4*sin(t*11.));col.r=mix(texture2D(tex,crop.xy+(ub+vec2(k,0.))*crop.zw).r,texture2D(tex,crop.xy+(ua+vec2(k,0.))*crop.zw).r,w);}
 float l=dot(col,vec3(.299,.587,.114));col*=1.+(ga-1.)*smoothstep(.05,.32,l);gl_FragColor=vec4(col,1.);}`;
  const all = new Set(), by = new WeakMap(); let raf = 0;
  class One {
    constructor(card, id) {
      this.card = card; this.id = id; this.scene = SCENES[id]; this.pic = card.querySelector(".pic"); this.img = this.pic && this.pic.querySelector("img"); this.cv = document.createElement("canvas"); this.cv.className = "alive"; this.cv.setAttribute("aria-hidden", "true");
      this.t0 = performance.now() - Math.random() * 4000; this.ok = false; this.w = 0; this.prep();
    }
    async prep() {
      const pic = this.pic, img = this.img; if (!pic || !img) return; try { if (!img.complete || !img.naturalWidth) await img.decode(); } catch (e) { return; }
      const w = pic.clientWidth, h = pic.clientHeight; if (!w || !h || !img.naturalWidth) return; const d = Math.min(devicePixelRatio || 1, 2); this.w = w; this.cv.width = Math.round(w * d); this.cv.height = Math.round(h * d);
      try {
        const gl = this.gl || this.cv.getContext("webgl", { antialias: false, alpha: false, preserveDrawingBuffer: false, powerPreference: "low-power" }); if (!gl) return; this.gl = gl;
        if (!this.prog) {
          const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
          const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error("link"); gl.useProgram(pr); this.prog = pr;
          const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW); const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
          const tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, img);
          const uc = new Float32Array(24), up = new Float32Array(24), uk = new Float32Array(6); this.scene.slice(0, 6).forEach((e, i) => { uk[i] = e[0]; uc.set(e.slice(1, 5), i * 4); for (let k = 0; k < 4; k++) up[i * 4 + k] = e[5 + k] || 0; });
          gl.uniform4fv(gl.getUniformLocation(pr, "uc"), uc); gl.uniform4fv(gl.getUniformLocation(pr, "up"), up); gl.uniform1fv(gl.getUniformLocation(pr, "uk"), uk); gl.uniform1f(gl.getUniformLocation(pr, "chroma"), CHROMA[this.id] || 0); this.ut = gl.getUniformLocation(pr, "t");
        }
        const ia = img.naturalWidth / img.naturalHeight, ca = w / h, crop = ia > ca ? [(1 - ca / ia) / 2, 0, ca / ia, 1] : [0, (1 - ia / ca) / 2, 1, ia / ca];                 // the picture fills its window the way the still one does
        gl.viewport(0, 0, this.cv.width, this.cv.height); gl.uniform4fv(gl.getUniformLocation(this.prog, "crop"), crop); gl.uniform1f(gl.getUniformLocation(this.prog, "asp"), ca);
        this.ok = true; this.frame(performance.now()); this.mount(); requestAnimationFrame(() => this.cv.classList.add("on"));
      } catch (e) { this.ok = false; }
    }
    mount() { if (this.pic && this.cv.parentNode !== this.pic) this.pic.appendChild(this.cv); }
    frame(now) { if (!this.ok) return; if (this.pic.clientWidth !== this.w) { this.ok = false; this.cv.classList.remove("on"); this.prep(); return; } const gl = this.gl; if (gl.isContextLost()) { this.ok = false; return; } gl.uniform1f(this.ut, (now - this.t0) / 1000); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); }
    drop() { try { const x = this.gl && this.gl.getExtension("WEBGL_lose_context"); if (x) x.loseContext(); } catch (e) {} this.cv.remove(); }
  }
  function loop(now) {
    raf = 0; if (!all.size) return;
    for (const o of [...all]) { if (!o.card.isConnected) { all.delete(o); by.delete(o.card); o.drop(); continue; } if (o.ok) o.mount(); if (!document.hidden && o.card.offsetParent !== null) o.frame(now); }
    if (all.size) raf = requestAnimationFrame(loop);
  }
  // bring a card's picture to life (safe to call again and again for the same card: it only puts the canvas back if the page was redrawn)
  function on(card, copy) {
    if (reduced || !card || !copy) return; const id = BY_NO[copy.no].id; if (typeof Glyph !== "undefined" && Glyph.has(id)) { Glyph.on(card, copy); return; } if (!SCENES[id]) return;
    let o = by.get(card); if (o && o.id !== id) { all.delete(o); o.drop(); o = null; } if (!o) { o = new One(card, id); by.set(card, o); all.add(o); } else if (o.ok) o.mount();
    if (!raf) raf = requestAnimationFrame(loop);
  }
  return { on, has: id => !!SCENES[id] };
})();
