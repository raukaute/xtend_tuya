function t(t,e,i,s){var r,n=arguments.length,o=n<3?e:null===s?s=Object.getOwnPropertyDescriptor(e,i):s;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)o=Reflect.decorate(t,e,i,s);else for(var a=t.length-1;a>=0;a--)(r=t[a])&&(o=(n<3?r(o):n>3?r(e,i,o):r(e,i))||o);return n>3&&o&&Object.defineProperty(e,i,o),o}"function"==typeof SuppressedError&&SuppressedError;
/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const e=globalThis,i=e.ShadowRoot&&(void 0===e.ShadyCSS||e.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,s=Symbol(),r=new WeakMap;let n=class{constructor(t,e,i){if(this._$cssResult$=!0,i!==s)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(i&&void 0===t){const i=void 0!==e&&1===e.length;i&&(t=r.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),i&&r.set(e,t))}return t}toString(){return this.cssText}};const o=i?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const i of t.cssRules)e+=i.cssText;return(t=>new n("string"==typeof t?t:t+"",void 0,s))(e)})(t):t,{is:a,defineProperty:c,getOwnPropertyDescriptor:l,getOwnPropertyNames:h,getOwnPropertySymbols:d,getPrototypeOf:p}=Object,u=globalThis,_=u.trustedTypes,g=_?_.emptyScript:"",f=u.reactiveElementPolyfillSupport,m=(t,e)=>t,v={toAttribute(t,e){switch(e){case Boolean:t=t?g:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t)}return t},fromAttribute(t,e){let i=t;switch(e){case Boolean:i=null!==t;break;case Number:i=null===t?null:Number(t);break;case Object:case Array:try{i=JSON.parse(t)}catch(t){i=null}}return i}},$=(t,e)=>!a(t,e),y={attribute:!0,type:String,converter:v,reflect:!1,useDefault:!1,hasChanged:$};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */Symbol.metadata??=Symbol("metadata"),u.litPropertyMetadata??=new WeakMap;let b=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=y){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const i=Symbol(),s=this.getPropertyDescriptor(t,i,e);void 0!==s&&c(this.prototype,t,s)}}static getPropertyDescriptor(t,e,i){const{get:s,set:r}=l(this.prototype,t)??{get(){return this[e]},set(t){this[e]=t}};return{get:s,set(e){const n=s?.call(this);r?.call(this,e),this.requestUpdate(t,n,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??y}static _$Ei(){if(this.hasOwnProperty(m("elementProperties")))return;const t=p(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(m("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(m("properties"))){const t=this.properties,e=[...h(t),...d(t)];for(const i of e)this.createProperty(i,t[i])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(const[t,e]of this.elementProperties){const i=this._$Eu(t,e);void 0!==i&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const i=new Set(t.flat(1/0).reverse());for(const t of i)e.unshift(o(t))}else void 0!==t&&e.push(o(t));return e}static _$Eu(t,e){const i=e.attribute;return!1===i?void 0:"string"==typeof i?i:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const i of e.keys())this.hasOwnProperty(i)&&(t.set(i,this[i]),delete this[i]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((t,s)=>{if(i)t.adoptedStyleSheets=s.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const i of s){const s=document.createElement("style"),r=e.litNonce;void 0!==r&&s.setAttribute("nonce",r),s.textContent=i.cssText,t.appendChild(s)}})(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,i){this._$AK(t,i)}_$ET(t,e){const i=this.constructor.elementProperties.get(t),s=this.constructor._$Eu(t,i);if(void 0!==s&&!0===i.reflect){const r=(void 0!==i.converter?.toAttribute?i.converter:v).toAttribute(e,i.type);this._$Em=t,null==r?this.removeAttribute(s):this.setAttribute(s,r),this._$Em=null}}_$AK(t,e){const i=this.constructor,s=i._$Eh.get(t);if(void 0!==s&&this._$Em!==s){const t=i.getPropertyOptions(s),r="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:v;this._$Em=s;const n=r.fromAttribute(e,t.type);this[s]=n??this._$Ej?.get(s)??n,this._$Em=null}}requestUpdate(t,e,i,s=!1,r){if(void 0!==t){const n=this.constructor;if(!1===s&&(r=this[t]),i??=n.getPropertyOptions(t),!((i.hasChanged??$)(r,e)||i.useDefault&&i.reflect&&r===this._$Ej?.get(t)&&!this.hasAttribute(n._$Eu(t,i))))return;this.C(t,e,i)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:i,reflect:s,wrapped:r},n){i&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,n??e??this[t]),!0!==r||void 0!==n)||(this._$AL.has(t)||(this.hasUpdated||i||(e=void 0),this._$AL.set(t,e)),!0===s&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,e]of this._$Ep)this[t]=e;this._$Ep=void 0}const t=this.constructor.elementProperties;if(t.size>0)for(const[e,i]of t){const{wrapped:t}=i,s=this[e];!0!==t||this._$AL.has(e)||void 0===s||this.C(e,void 0,i,s)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(e){throw t=!1,this._$EM(),e}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(t){}firstUpdated(t){}};b.elementStyles=[],b.shadowRootOptions={mode:"open"},b[m("elementProperties")]=new Map,b[m("finalized")]=new Map,f?.({ReactiveElement:b}),(u.reactiveElementVersions??=[]).push("2.1.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const A=globalThis,w=t=>t,x=A.trustedTypes,S=x?x.createPolicy("lit-html",{createHTML:t=>t}):void 0,E="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,P="?"+C,M=`<${P}>`,k=document,O=()=>k.createComment(""),T=t=>null===t||"object"!=typeof t&&"function"!=typeof t,H=Array.isArray,U="[ \t\n\f\r]",N=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,R=/-->/g,z=/>/g,D=RegExp(`>|${U}(?:([^\\s"'>=/]+)(${U}*=${U}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),j=/'/g,L=/"/g,F=/^(?:script|style|textarea|title)$/i,I=(t=>(e,...i)=>({_$litType$:t,strings:e,values:i}))(1),V=Symbol.for("lit-noChange"),B=Symbol.for("lit-nothing"),W=new WeakMap,q=k.createTreeWalker(k,129);function J(t,e){if(!H(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==S?S.createHTML(e):e}const K=(t,e)=>{const i=t.length-1,s=[];let r,n=2===e?"<svg>":3===e?"<math>":"",o=N;for(let e=0;e<i;e++){const i=t[e];let a,c,l=-1,h=0;for(;h<i.length&&(o.lastIndex=h,c=o.exec(i),null!==c);)h=o.lastIndex,o===N?"!--"===c[1]?o=R:void 0!==c[1]?o=z:void 0!==c[2]?(F.test(c[2])&&(r=RegExp("</"+c[2],"g")),o=D):void 0!==c[3]&&(o=D):o===D?">"===c[0]?(o=r??N,l=-1):void 0===c[1]?l=-2:(l=o.lastIndex-c[2].length,a=c[1],o=void 0===c[3]?D:'"'===c[3]?L:j):o===L||o===j?o=D:o===R||o===z?o=N:(o=D,r=void 0);const d=o===D&&t[e+1].startsWith("/>")?" ":"";n+=o===N?i+M:l>=0?(s.push(a),i.slice(0,l)+E+i.slice(l)+C+d):i+C+(-2===l?e:d)}return[J(t,n+(t[i]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),s]};class Z{constructor({strings:t,_$litType$:e},i){let s;this.parts=[];let r=0,n=0;const o=t.length-1,a=this.parts,[c,l]=K(t,e);if(this.el=Z.createElement(c,i),q.currentNode=this.el.content,2===e||3===e){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes)}for(;null!==(s=q.nextNode())&&a.length<o;){if(1===s.nodeType){if(s.hasAttributes())for(const t of s.getAttributeNames())if(t.endsWith(E)){const e=l[n++],i=s.getAttribute(t).split(C),o=/([.?@])?(.*)/.exec(e);a.push({type:1,index:r,name:o[2],strings:i,ctor:"."===o[1]?tt:"?"===o[1]?et:"@"===o[1]?it:Y}),s.removeAttribute(t)}else t.startsWith(C)&&(a.push({type:6,index:r}),s.removeAttribute(t));if(F.test(s.tagName)){const t=s.textContent.split(C),e=t.length-1;if(e>0){s.textContent=x?x.emptyScript:"";for(let i=0;i<e;i++)s.append(t[i],O()),q.nextNode(),a.push({type:2,index:++r});s.append(t[e],O())}}}else if(8===s.nodeType)if(s.data===P)a.push({type:2,index:r});else{let t=-1;for(;-1!==(t=s.data.indexOf(C,t+1));)a.push({type:7,index:r}),t+=C.length-1}r++}}static createElement(t,e){const i=k.createElement("template");return i.innerHTML=t,i}}function G(t,e,i=t,s){if(e===V)return e;let r=void 0!==s?i._$Co?.[s]:i._$Cl;const n=T(e)?void 0:e._$litDirective$;return r?.constructor!==n&&(r?._$AO?.(!1),void 0===n?r=void 0:(r=new n(t),r._$AT(t,i,s)),void 0!==s?(i._$Co??=[])[s]=r:i._$Cl=r),void 0!==r&&(e=G(t,r._$AS(t,e.values),r,s)),e}class Q{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:i}=this._$AD,s=(t?.creationScope??k).importNode(e,!0);q.currentNode=s;let r=q.nextNode(),n=0,o=0,a=i[0];for(;void 0!==a;){if(n===a.index){let e;2===a.type?e=new X(r,r.nextSibling,this,t):1===a.type?e=new a.ctor(r,a.name,a.strings,this,t):6===a.type&&(e=new st(r,this,t)),this._$AV.push(e),a=i[++o]}n!==a?.index&&(r=q.nextNode(),n++)}return q.currentNode=k,s}p(t){let e=0;for(const i of this._$AV)void 0!==i&&(void 0!==i.strings?(i._$AI(t,i,e),e+=i.strings.length-2):i._$AI(t[e])),e++}}class X{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,i,s){this.type=2,this._$AH=B,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=i,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=G(this,t,e),T(t)?t===B||null==t||""===t?(this._$AH!==B&&this._$AR(),this._$AH=B):t!==this._$AH&&t!==V&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):(t=>H(t)||"function"==typeof t?.[Symbol.iterator])(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==B&&T(this._$AH)?this._$AA.nextSibling.data=t:this.T(k.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:i}=t,s="number"==typeof i?this._$AC(t):(void 0===i.el&&(i.el=Z.createElement(J(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===s)this._$AH.p(e);else{const t=new Q(s,this),i=t.u(this.options);t.p(e),this.T(i),this._$AH=t}}_$AC(t){let e=W.get(t.strings);return void 0===e&&W.set(t.strings,e=new Z(t)),e}k(t){H(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let i,s=0;for(const r of t)s===e.length?e.push(i=new X(this.O(O()),this.O(O()),this,this.options)):i=e[s],i._$AI(r),s++;s<e.length&&(this._$AR(i&&i._$AB.nextSibling,s),e.length=s)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const e=w(t).nextSibling;w(t).remove(),t=e}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}}class Y{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,i,s,r){this.type=1,this._$AH=B,this._$AN=void 0,this.element=t,this.name=e,this._$AM=s,this.options=r,i.length>2||""!==i[0]||""!==i[1]?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=B}_$AI(t,e=this,i,s){const r=this.strings;let n=!1;if(void 0===r)t=G(this,t,e,0),n=!T(t)||t!==this._$AH&&t!==V,n&&(this._$AH=t);else{const s=t;let o,a;for(t=r[0],o=0;o<r.length-1;o++)a=G(this,s[i+o],e,o),a===V&&(a=this._$AH[o]),n||=!T(a)||a!==this._$AH[o],a===B?t=B:t!==B&&(t+=(a??"")+r[o+1]),this._$AH[o]=a}n&&!s&&this.j(t)}j(t){t===B?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class tt extends Y{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===B?void 0:t}}class et extends Y{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==B)}}class it extends Y{constructor(t,e,i,s,r){super(t,e,i,s,r),this.type=5}_$AI(t,e=this){if((t=G(this,t,e,0)??B)===V)return;const i=this._$AH,s=t===B&&i!==B||t.capture!==i.capture||t.once!==i.once||t.passive!==i.passive,r=t!==B&&(i===B||s);s&&this.element.removeEventListener(this.name,this,i),r&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class st{constructor(t,e,i){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(t){G(this,t)}}const rt=A.litHtmlPolyfillSupport;rt?.(Z,X),(A.litHtmlVersions??=[]).push("3.3.2");const nt=globalThis;
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */class ot extends b{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=((t,e,i)=>{const s=i?.renderBefore??e;let r=s._$litPart$;if(void 0===r){const t=i?.renderBefore??null;s._$litPart$=r=new X(e.insertBefore(O(),t),t,void 0,i??{})}return r._$AI(t),r})(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return V}}ot._$litElement$=!0,ot.finalized=!0,nt.litElementHydrateSupport?.({LitElement:ot});const at=nt.litElementPolyfillSupport;at?.({LitElement:ot}),(nt.litElementVersions??=[]).push("4.2.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const ct={attribute:!0,type:String,converter:v,reflect:!1,hasChanged:$},lt=(t=ct,e,i)=>{const{kind:s,metadata:r}=i;let n=globalThis.litPropertyMetadata.get(r);if(void 0===n&&globalThis.litPropertyMetadata.set(r,n=new Map),"setter"===s&&((t=Object.create(t)).wrapped=!0),n.set(i.name,t),"accessor"===s){const{name:s}=i;return{set(i){const r=e.get.call(this);e.set.call(this,i),this.requestUpdate(s,r,t,!0,i)},init(e){return void 0!==e&&this.C(s,void 0,t,e),e}}}if("setter"===s){const{name:s}=i;return function(i){const r=this[s];e.call(this,i),this.requestUpdate(s,r,t,!0,i)}}throw Error("Unsupported decorator location: "+s)};function ht(t){return(e,i)=>"object"==typeof i?lt(t,e,i):((t,e,i)=>{const s=e.hasOwnProperty(i);return e.constructor.createProperty(i,t),s?Object.getOwnPropertyDescriptor(e,i):void 0})(t,e,i)}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function dt(t){return ht({...t,state:!0,attribute:!1})}class pt extends ot{constructor(){super(...arguments),this._mode="duration",this._target=60,this._initiatedHere=!1,this._tick=0,this._tickHandle=null}setConfig(t){if(!t.valve)throw new Error("Please define a valve switch entity");if(!t.device_id)throw new Error("Please define a device_id");this._config=t}getCardSize(){return 3}connectedCallback(){super.connectedCallback(),this._tickHandle=window.setInterval(()=>this._tick=Date.now(),1e3)}disconnectedCallback(){super.disconnectedCallback(),null!==this._tickHandle&&(window.clearInterval(this._tickHandle),this._tickHandle=null)}updated(t){t.has("hass")&&this.hass&&this._config&&void 0===t.get("hass")&&this._initTargetFromState()}_initTargetFromState(){if(!this._config.duration)return;const t=this.hass.states[this._config.duration];if(!t)return;const e=parseFloat(t.state);Number.isFinite(e)&&e>0&&(this._target=e)}_isOn(){const t=this.hass.states[this._config.valve];return"on"===t?.state}_activeMode(){if(!this._config.mode_sensor)return null;const t=this.hass.states[this._config.mode_sensor];return t?"duration"===t.state?"duration":"volume"===t.state?"volume":null:null}_targetValue(){if(!this._config.value_sensor)return null;const t=this.hass.states[this._config.value_sensor];if(!t)return null;const e=parseFloat(t.state);return Number.isFinite(e)?e:null}_startTime(){if(!this._config.start_time_sensor)return null;const t=this.hass.states[this._config.start_time_sensor];if(!t||!t.state)return null;const e=new Date(t.state.replace(" ","T"));return Number.isFinite(e.getTime())?e:null}_endTime(){if(!this._config.end_time_sensor)return null;const t=this.hass.states[this._config.end_time_sensor];if(!t||!t.state)return null;const e=new Date(t.state.replace(" ","T"));return Number.isFinite(e.getTime())?e:null}_currentVolume(){if(!this._config.volume_sensor)return null;const t=this.hass.states[this._config.volume_sensor];if(!t)return null;const e=parseFloat(t.state);return Number.isFinite(e)?e:null}_valveName(){if(!this._config.registry_entity)return null;const t=this.hass.states[this._config.registry_entity];return t?.attributes?.valve_name??null}async _toggleManual(){if(!this.hass)return;this._initiatedHere=!1;const t=this._isOn()?"turn_off":"turn_on";await this.hass.callService("switch",t,{entity_id:this._config.valve})}async _startSingleWatering(){if(this.hass){this._initiatedHere=!0;try{await this.hass.callService("xtend_tuya","fdm5kw_start_watering",{device_id:this._config.device_id,mode:this._mode,value:Math.max(1,Math.round(this._target))})}catch(t){throw this._initiatedHere=!1,t}}}async _stop(){if(this.hass){this._initiatedHere=!1;try{await this.hass.callService("xtend_tuya","fdm5kw_stop_watering",{device_id:this._config.device_id})}catch{await this.hass.callService("switch","turn_off",{entity_id:this._config.valve})}}}render(){if(!this._config||!this.hass)return B;const t=this._config.name??this._valveName()??this.hass.states[this._config.valve]?.attributes?.friendly_name??"Watering",e=this._isOn(),i=this._startTime(),s=this._endTime(),r=this._initiatedHere&&e&&null!==i&&(null===s||i>s);return I`
      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:water-pump"></ha-icon>
          <span>${t}</span>
          ${this._renderStatusPill(e,r)}
        </div>
        <div class="card-content">
          ${r?this._renderProgress(i):this._renderControls()}
        </div>
      </ha-card>
    `}_renderStatusPill(t,e){return e?I`<span class="pill running">Watering</span>`:t?I`<span class="pill manual">Manual ON</span>`:I`<span class="pill idle">Idle</span>`}_renderProgress(t){this._tick;const e=this._activeMode()??this._mode,i=this._targetValue()??this._target;if("volume"===e){const t=this._currentVolume()??0,e=i>0?Math.min(100,t/i*100):0,s=Math.max(0,i-t);return I`
        <div class="progress">
          <div class="progress-text">
            <span class="big">${t.toFixed(1)} L</span>
            <span class="dim"> / ${i} L</span>
          </div>
          <div class="bar">
            <div class="fill" style="width:${e}%"></div>
          </div>
          <div class="progress-sub">${s.toFixed(1)} L remaining</div>
        </div>
        <button class="stop-btn" @click=${this._stop}>Stop</button>
      `}const s=(Date.now()-t.getTime())/1e3,r=Math.max(0,Math.min(i,s)),n=i>0?Math.min(100,r/i*100):0,o=Math.max(0,i-r);return I`
      <div class="progress">
        <div class="progress-text">
          <span class="big">${ut(o)}</span>
          <span class="dim"> left of ${ut(i)}</span>
        </div>
        <div class="bar">
          <div class="fill" style="width:${n}%"></div>
        </div>
        <div class="progress-sub">
          ${ut(r)} elapsed
        </div>
      </div>
      <button class="stop-btn" @click=${this._stop}>Stop</button>
    `}_renderControls(){return I`
      <div class="mode-tabs">
        <button
          class=${"duration"===this._mode?"tab active":"tab"}
          @click=${()=>this._setMode("duration")}
        >
          <ha-icon icon="mdi:timer-outline"></ha-icon>
          Duration
        </button>
        <button
          class=${"volume"===this._mode?"tab active":"tab"}
          @click=${()=>this._setMode("volume")}
        >
          <ha-icon icon="mdi:water"></ha-icon>
          Volume
        </button>
      </div>

      <div class="target-row">
        <label>${"duration"===this._mode?"Duration":"Volume"}</label>
        <div class="target-input">
          <input
            type="number"
            min="1"
            max=${"duration"===this._mode?86400:9999}
            .value=${String("duration"===this._mode?Math.max(1,Math.round(this._target)):this._target)}
            @change=${t=>{const e=parseFloat(t.target.value);Number.isFinite(e)&&e>0&&(this._target=e)}}
          />
          <span class="unit">${"duration"===this._mode?"sec":"L"}</span>
          <button class="start-btn inline" @click=${this._startSingleWatering}>
            <ha-icon icon="mdi:play"></ha-icon>
            Single watering
          </button>
        </div>
      </div>

      <div class="primary-actions">
        <button
          class="manual-btn ${this._isOn()?"on":""}"
          @click=${this._toggleManual}
          title=${this._isOn()?"Manually stop the valve":"Manually open the valve (no auto-stop)"}
        >
          <ha-icon icon=${this._isOn()?"mdi:toggle-switch":"mdi:toggle-switch-off-outline"}></ha-icon>
          Manual ${this._isOn()?"OFF":"ON"}
        </button>
      </div>
    `}_setMode(t){this._mode!==t&&("duration"===t&&this._target<5&&(this._target=60),"volume"===t&&this._target>1e3&&(this._target=10),this._mode=t)}}function ut(t){if(!Number.isFinite(t)||t<0)return"0:00";const e=Math.round(t),i=Math.floor(e/3600),s=Math.floor(e%3600/60),r=e%60;return i>0?`${i}:${String(s).padStart(2,"0")}:${String(r).padStart(2,"0")}`:`${s}:${String(r).padStart(2,"0")}`}if(pt.styles=((t,...e)=>{const i=1===t.length?t[0]:e.reduce((e,i,s)=>e+(t=>{if(!0===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+t[s+1],t[0]);return new n(i,t,s)})`
    :host {
      --ic-primary: var(--primary-color, #03a9f4);
      --ic-bg: var(--card-background-color, #fff);
      --ic-text: var(--primary-text-color, #212121);
      --ic-secondary: var(--secondary-text-color, #727272);
      --ic-divider: var(--divider-color, #e0e0e0);
      --ic-success: var(--success-color, #4caf50);
      --ic-warning: var(--warning-color, #ff9800);
    }

    .card-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px 16px 0;
      font-size: 1.1em;
      font-weight: 500;
      color: var(--ic-text);
    }

    .card-header ha-icon {
      color: var(--ic-primary);
    }

    .card-header span {
      flex: 1;
    }

    .pill {
      font-size: 0.75em;
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .pill.idle {
      background: var(--ic-divider);
      color: var(--ic-secondary);
    }
    .pill.running {
      background: var(--ic-primary);
      color: white;
    }
    .pill.manual {
      background: var(--ic-warning);
      color: white;
    }

    .card-content {
      padding: 16px;
    }

    /* Mode tabs */
    .mode-tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }
    .tab {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 10px;
      border: 1px solid var(--ic-divider);
      border-radius: 8px;
      background: transparent;
      color: var(--ic-secondary);
      font-size: 0.95em;
      cursor: pointer;
    }
    .tab.active {
      background: var(--ic-primary);
      color: white;
      border-color: var(--ic-primary);
    }

    /* Target input */
    .target-row {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-bottom: 12px;
    }
    .target-row label {
      font-size: 0.85em;
      font-weight: 500;
      color: var(--ic-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .target-input {
      display: flex;
      align-items: stretch;
      gap: 8px;
    }
    .target-input input {
      flex: 1;
      min-width: 0;
      padding: 10px 12px;
      border: 1px solid var(--ic-divider);
      border-radius: 8px;
      background: var(--ic-bg);
      color: var(--ic-text);
      font-size: 1.1em;
      outline: none;
    }
    .target-input input:focus {
      border-color: var(--ic-primary);
    }
    .target-input .unit {
      align-self: center;
      color: var(--ic-secondary);
      font-size: 0.95em;
    }
    .target-input .start-btn.inline {
      flex: 0 0 auto;
      padding: 0 14px;
      white-space: nowrap;
    }

    /* Primary actions */
    .primary-actions {
      display: flex;
      gap: 8px;
    }
    .start-btn,
    .manual-btn,
    .stop-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 12px;
      border: none;
      border-radius: 8px;
      font-size: 0.95em;
      font-weight: 500;
      cursor: pointer;
    }
    .start-btn {
      background: var(--ic-primary);
      color: white;
    }
    .manual-btn {
      flex: 1;
      background: transparent;
      border: 1px solid var(--ic-divider);
      color: var(--ic-text);
    }
    .manual-btn.on {
      background: var(--ic-warning);
      color: white;
      border-color: var(--ic-warning);
    }
    .stop-btn {
      width: 100%;
      margin-top: 16px;
      background: transparent;
      border: 1px solid var(--ic-divider);
      color: var(--ic-text);
    }

    .dim {
      color: var(--ic-secondary);
    }

    /* Progress view */
    .progress {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .progress-text {
      display: flex;
      align-items: baseline;
      gap: 4px;
      font-variant-numeric: tabular-nums;
    }
    .progress-text .big {
      font-size: 2em;
      font-weight: 600;
      color: var(--ic-text);
    }
    .progress-text .dim {
      font-size: 1em;
    }
    .bar {
      height: 8px;
      background: var(--ic-divider);
      border-radius: 4px;
      overflow: hidden;
    }
    .fill {
      height: 100%;
      background: var(--ic-primary);
      transition: width 0.5s linear;
    }
    .progress-sub {
      font-size: 0.85em;
      color: var(--ic-secondary);
    }
  `,t([ht({attribute:!1})],pt.prototype,"hass",void 0),t([dt()],pt.prototype,"_config",void 0),t([dt()],pt.prototype,"_mode",void 0),t([dt()],pt.prototype,"_target",void 0),t([dt()],pt.prototype,"_initiatedHere",void 0),t([dt()],pt.prototype,"_tick",void 0),!customElements.get("irrigation-control-card")){customElements.define("irrigation-control-card",pt);const t=window;t.customCards=t.customCards||[],t.customCards.some(t=>"irrigation-control-card"===t.type)||t.customCards.push({type:"irrigation-control-card",name:"Irrigation Control",description:"Toggle a valve, start a single watering cycle by duration or volume, and watch progress live."})}export{pt as IrrigationControlCard};
