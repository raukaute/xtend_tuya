function t(t,e,i,s){var r,o=arguments.length,n=o<3?e:null===s?s=Object.getOwnPropertyDescriptor(e,i):s;if("object"==typeof Reflect&&"function"==typeof Reflect.decorate)n=Reflect.decorate(t,e,i,s);else for(var a=t.length-1;a>=0;a--)(r=t[a])&&(n=(o<3?r(n):o>3?r(e,i,n):r(e,i))||n);return o>3&&n&&Object.defineProperty(e,i,n),n}"function"==typeof SuppressedError&&SuppressedError;
/**
 * @license
 * Copyright 2019 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const e=globalThis,i=e.ShadowRoot&&(void 0===e.ShadyCSS||e.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,s=Symbol(),r=new WeakMap;let o=class{constructor(t,e,i){if(this._$cssResult$=!0,i!==s)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o;const e=this.t;if(i&&void 0===t){const i=void 0!==e&&1===e.length;i&&(t=r.get(e)),void 0===t&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),i&&r.set(e,t))}return t}toString(){return this.cssText}};const n=i?t=>t:t=>t instanceof CSSStyleSheet?(t=>{let e="";for(const i of t.cssRules)e+=i.cssText;return(t=>new o("string"==typeof t?t:t+"",void 0,s))(e)})(t):t,{is:a,defineProperty:d,getOwnPropertyDescriptor:c,getOwnPropertyNames:l,getOwnPropertySymbols:h,getPrototypeOf:p}=Object,u=globalThis,m=u.trustedTypes,_=m?m.emptyScript:"",f=u.reactiveElementPolyfillSupport,$=(t,e)=>t,v={toAttribute(t,e){switch(e){case Boolean:t=t?_:null;break;case Object:case Array:t=null==t?t:JSON.stringify(t)}return t},fromAttribute(t,e){let i=t;switch(e){case Boolean:i=null!==t;break;case Number:i=null===t?null:Number(t);break;case Object:case Array:try{i=JSON.parse(t)}catch(t){i=null}}return i}},g=(t,e)=>!a(t,e),y={attribute:!0,type:String,converter:v,reflect:!1,useDefault:!1,hasChanged:g};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */Symbol.metadata??=Symbol("metadata"),u.litPropertyMetadata??=new WeakMap;let b=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=y){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){const i=Symbol(),s=this.getPropertyDescriptor(t,i,e);void 0!==s&&d(this.prototype,t,s)}}static getPropertyDescriptor(t,e,i){const{get:s,set:r}=c(this.prototype,t)??{get(){return this[e]},set(t){this[e]=t}};return{get:s,set(e){const o=s?.call(this);r?.call(this,e),this.requestUpdate(t,o,i)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??y}static _$Ei(){if(this.hasOwnProperty($("elementProperties")))return;const t=p(this);t.finalize(),void 0!==t.l&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty($("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty($("properties"))){const t=this.properties,e=[...l(t),...h(t)];for(const i of e)this.createProperty(i,t[i])}const t=this[Symbol.metadata];if(null!==t){const e=litPropertyMetadata.get(t);if(void 0!==e)for(const[t,i]of e)this.elementProperties.set(t,i)}this._$Eh=new Map;for(const[t,e]of this.elementProperties){const i=this._$Eu(t,e);void 0!==i&&this._$Eh.set(i,t)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){const e=[];if(Array.isArray(t)){const i=new Set(t.flat(1/0).reverse());for(const t of i)e.unshift(n(t))}else void 0!==t&&e.push(n(t));return e}static _$Eu(t,e){const i=e.attribute;return!1===i?void 0:"string"==typeof i?i:"string"==typeof t?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),void 0!==this.renderRoot&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){const t=new Map,e=this.constructor.elementProperties;for(const i of e.keys())this.hasOwnProperty(i)&&(t.set(i,this[i]),delete this[i]);t.size>0&&(this._$Ep=t)}createRenderRoot(){const t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return((t,s)=>{if(i)t.adoptedStyleSheets=s.map(t=>t instanceof CSSStyleSheet?t:t.styleSheet);else for(const i of s){const s=document.createElement("style"),r=e.litNonce;void 0!==r&&s.setAttribute("nonce",r),s.textContent=i.cssText,t.appendChild(s)}})(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,i){this._$AK(t,i)}_$ET(t,e){const i=this.constructor.elementProperties.get(t),s=this.constructor._$Eu(t,i);if(void 0!==s&&!0===i.reflect){const r=(void 0!==i.converter?.toAttribute?i.converter:v).toAttribute(e,i.type);this._$Em=t,null==r?this.removeAttribute(s):this.setAttribute(s,r),this._$Em=null}}_$AK(t,e){const i=this.constructor,s=i._$Eh.get(t);if(void 0!==s&&this._$Em!==s){const t=i.getPropertyOptions(s),r="function"==typeof t.converter?{fromAttribute:t.converter}:void 0!==t.converter?.fromAttribute?t.converter:v;this._$Em=s;const o=r.fromAttribute(e,t.type);this[s]=o??this._$Ej?.get(s)??o,this._$Em=null}}requestUpdate(t,e,i,s=!1,r){if(void 0!==t){const o=this.constructor;if(!1===s&&(r=this[t]),i??=o.getPropertyOptions(t),!((i.hasChanged??g)(r,e)||i.useDefault&&i.reflect&&r===this._$Ej?.get(t)&&!this.hasAttribute(o._$Eu(t,i))))return;this.C(t,e,i)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(t,e,{useDefault:i,reflect:s,wrapped:r},o){i&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,o??e??this[t]),!0!==r||void 0!==o)||(this._$AL.has(t)||(this.hasUpdated||i||(e=void 0),this._$AL.set(t,e)),!0===s&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(t){Promise.reject(t)}const t=this.scheduleUpdate();return null!=t&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(const[t,e]of this._$Ep)this[t]=e;this._$Ep=void 0}const t=this.constructor.elementProperties;if(t.size>0)for(const[e,i]of t){const{wrapped:t}=i,s=this[e];!0!==t||this._$AL.has(e)||void 0===s||this.C(e,void 0,i,s)}}let t=!1;const e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(t=>t.hostUpdate?.()),this.update(e)):this._$EM()}catch(e){throw t=!1,this._$EM(),e}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(t=>t.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(t=>this._$ET(t,this[t])),this._$EM()}updated(t){}firstUpdated(t){}};b.elementStyles=[],b.shadowRootOptions={mode:"open"},b[$("elementProperties")]=new Map,b[$("finalized")]=new Map,f?.({ReactiveElement:b}),(u.reactiveElementVersions??=[]).push("2.1.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const A=globalThis,w=t=>t,x=A.trustedTypes,E=x?x.createPolicy("lit-html",{createHTML:t=>t}):void 0,S="$lit$",C=`lit$${Math.random().toFixed(9).slice(2)}$`,P="?"+C,T=`<${P}>`,M=document,k=()=>M.createComment(""),U=t=>null===t||"object"!=typeof t&&"function"!=typeof t,O=Array.isArray,N="[ \t\n\f\r]",D=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,H=/-->/g,R=/>/g,z=RegExp(`>|${N}(?:([^\\s"'>=/]+)(${N}*=${N}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,"g"),j=/'/g,L=/"/g,I=/^(?:script|style|textarea|title)$/i,V=(t=>(e,...i)=>({_$litType$:t,strings:e,values:i}))(1),B=Symbol.for("lit-noChange"),W=Symbol.for("lit-nothing"),q=new WeakMap,F=M.createTreeWalker(M,129);function J(t,e){if(!O(t)||!t.hasOwnProperty("raw"))throw Error("invalid template strings array");return void 0!==E?E.createHTML(e):e}const K=(t,e)=>{const i=t.length-1,s=[];let r,o=2===e?"<svg>":3===e?"<math>":"",n=D;for(let e=0;e<i;e++){const i=t[e];let a,d,c=-1,l=0;for(;l<i.length&&(n.lastIndex=l,d=n.exec(i),null!==d);)l=n.lastIndex,n===D?"!--"===d[1]?n=H:void 0!==d[1]?n=R:void 0!==d[2]?(I.test(d[2])&&(r=RegExp("</"+d[2],"g")),n=z):void 0!==d[3]&&(n=z):n===z?">"===d[0]?(n=r??D,c=-1):void 0===d[1]?c=-2:(c=n.lastIndex-d[2].length,a=d[1],n=void 0===d[3]?z:'"'===d[3]?L:j):n===L||n===j?n=z:n===H||n===R?n=D:(n=z,r=void 0);const h=n===z&&t[e+1].startsWith("/>")?" ":"";o+=n===D?i+T:c>=0?(s.push(a),i.slice(0,c)+S+i.slice(c)+C+h):i+C+(-2===c?e:h)}return[J(t,o+(t[i]||"<?>")+(2===e?"</svg>":3===e?"</math>":"")),s]};class Z{constructor({strings:t,_$litType$:e},i){let s;this.parts=[];let r=0,o=0;const n=t.length-1,a=this.parts,[d,c]=K(t,e);if(this.el=Z.createElement(d,i),F.currentNode=this.el.content,2===e||3===e){const t=this.el.content.firstChild;t.replaceWith(...t.childNodes)}for(;null!==(s=F.nextNode())&&a.length<n;){if(1===s.nodeType){if(s.hasAttributes())for(const t of s.getAttributeNames())if(t.endsWith(S)){const e=c[o++],i=s.getAttribute(t).split(C),n=/([.?@])?(.*)/.exec(e);a.push({type:1,index:r,name:n[2],strings:i,ctor:"."===n[1]?tt:"?"===n[1]?et:"@"===n[1]?it:Y}),s.removeAttribute(t)}else t.startsWith(C)&&(a.push({type:6,index:r}),s.removeAttribute(t));if(I.test(s.tagName)){const t=s.textContent.split(C),e=t.length-1;if(e>0){s.textContent=x?x.emptyScript:"";for(let i=0;i<e;i++)s.append(t[i],k()),F.nextNode(),a.push({type:2,index:++r});s.append(t[e],k())}}}else if(8===s.nodeType)if(s.data===P)a.push({type:2,index:r});else{let t=-1;for(;-1!==(t=s.data.indexOf(C,t+1));)a.push({type:7,index:r}),t+=C.length-1}r++}}static createElement(t,e){const i=M.createElement("template");return i.innerHTML=t,i}}function G(t,e,i=t,s){if(e===B)return e;let r=void 0!==s?i._$Co?.[s]:i._$Cl;const o=U(e)?void 0:e._$litDirective$;return r?.constructor!==o&&(r?._$AO?.(!1),void 0===o?r=void 0:(r=new o(t),r._$AT(t,i,s)),void 0!==s?(i._$Co??=[])[s]=r:i._$Cl=r),void 0!==r&&(e=G(t,r._$AS(t,e.values),r,s)),e}class Q{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){const{el:{content:e},parts:i}=this._$AD,s=(t?.creationScope??M).importNode(e,!0);F.currentNode=s;let r=F.nextNode(),o=0,n=0,a=i[0];for(;void 0!==a;){if(o===a.index){let e;2===a.type?e=new X(r,r.nextSibling,this,t):1===a.type?e=new a.ctor(r,a.name,a.strings,this,t):6===a.type&&(e=new st(r,this,t)),this._$AV.push(e),a=i[++n]}o!==a?.index&&(r=F.nextNode(),o++)}return F.currentNode=M,s}p(t){let e=0;for(const i of this._$AV)void 0!==i&&(void 0!==i.strings?(i._$AI(t,i,e),e+=i.strings.length-2):i._$AI(t[e])),e++}}class X{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,i,s){this.type=2,this._$AH=W,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=i,this.options=s,this._$Cv=s?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode;const e=this._$AM;return void 0!==e&&11===t?.nodeType&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=G(this,t,e),U(t)?t===W||null==t||""===t?(this._$AH!==W&&this._$AR(),this._$AH=W):t!==this._$AH&&t!==B&&this._(t):void 0!==t._$litType$?this.$(t):void 0!==t.nodeType?this.T(t):(t=>O(t)||"function"==typeof t?.[Symbol.iterator])(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==W&&U(this._$AH)?this._$AA.nextSibling.data=t:this.T(M.createTextNode(t)),this._$AH=t}$(t){const{values:e,_$litType$:i}=t,s="number"==typeof i?this._$AC(t):(void 0===i.el&&(i.el=Z.createElement(J(i.h,i.h[0]),this.options)),i);if(this._$AH?._$AD===s)this._$AH.p(e);else{const t=new Q(s,this),i=t.u(this.options);t.p(e),this.T(i),this._$AH=t}}_$AC(t){let e=q.get(t.strings);return void 0===e&&q.set(t.strings,e=new Z(t)),e}k(t){O(this._$AH)||(this._$AH=[],this._$AR());const e=this._$AH;let i,s=0;for(const r of t)s===e.length?e.push(i=new X(this.O(k()),this.O(k()),this,this.options)):i=e[s],i._$AI(r),s++;s<e.length&&(this._$AR(i&&i._$AB.nextSibling,s),e.length=s)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){const e=w(t).nextSibling;w(t).remove(),t=e}}setConnected(t){void 0===this._$AM&&(this._$Cv=t,this._$AP?.(t))}}class Y{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,i,s,r){this.type=1,this._$AH=W,this._$AN=void 0,this.element=t,this.name=e,this._$AM=s,this.options=r,i.length>2||""!==i[0]||""!==i[1]?(this._$AH=Array(i.length-1).fill(new String),this.strings=i):this._$AH=W}_$AI(t,e=this,i,s){const r=this.strings;let o=!1;if(void 0===r)t=G(this,t,e,0),o=!U(t)||t!==this._$AH&&t!==B,o&&(this._$AH=t);else{const s=t;let n,a;for(t=r[0],n=0;n<r.length-1;n++)a=G(this,s[i+n],e,n),a===B&&(a=this._$AH[n]),o||=!U(a)||a!==this._$AH[n],a===W?t=W:t!==W&&(t+=(a??"")+r[n+1]),this._$AH[n]=a}o&&!s&&this.j(t)}j(t){t===W?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}}class tt extends Y{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===W?void 0:t}}class et extends Y{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==W)}}class it extends Y{constructor(t,e,i,s,r){super(t,e,i,s,r),this.type=5}_$AI(t,e=this){if((t=G(this,t,e,0)??W)===B)return;const i=this._$AH,s=t===W&&i!==W||t.capture!==i.capture||t.once!==i.once||t.passive!==i.passive,r=t!==W&&(i===W||s);s&&this.element.removeEventListener(this.name,this,i),r&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){"function"==typeof this._$AH?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}}class st{constructor(t,e,i){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=i}get _$AU(){return this._$AM._$AU}_$AI(t){G(this,t)}}const rt=A.litHtmlPolyfillSupport;rt?.(Z,X),(A.litHtmlVersions??=[]).push("3.3.2");const ot=globalThis;
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */class nt extends b{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){const t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){const e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=((t,e,i)=>{const s=i?.renderBefore??e;let r=s._$litPart$;if(void 0===r){const t=i?.renderBefore??null;s._$litPart$=r=new X(e.insertBefore(k(),t),t,void 0,i??{})}return r._$AI(t),r})(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return B}}nt._$litElement$=!0,nt.finalized=!0,ot.litElementHydrateSupport?.({LitElement:nt});const at=ot.litElementPolyfillSupport;at?.({LitElement:nt}),(ot.litElementVersions??=[]).push("4.2.2");
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */
const dt={attribute:!0,type:String,converter:v,reflect:!1,hasChanged:g},ct=(t=dt,e,i)=>{const{kind:s,metadata:r}=i;let o=globalThis.litPropertyMetadata.get(r);if(void 0===o&&globalThis.litPropertyMetadata.set(r,o=new Map),"setter"===s&&((t=Object.create(t)).wrapped=!0),o.set(i.name,t),"accessor"===s){const{name:s}=i;return{set(i){const r=e.get.call(this);e.set.call(this,i),this.requestUpdate(s,r,t,!0,i)},init(e){return void 0!==e&&this.C(s,void 0,t,e),e}}}if("setter"===s){const{name:s}=i;return function(i){const r=this[s];e.call(this,i),this.requestUpdate(s,r,t,!0,i)}}throw Error("Unsupported decorator location: "+s)};
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function lt(t){return(e,i)=>"object"==typeof i?ct(t,e,i):((t,e,i)=>{const s=e.hasOwnProperty(i);return e.constructor.createProperty(i,t),s?Object.getOwnPropertyDescriptor(e,i):void 0})(t,e,i)}
/**
 * @license
 * Copyright 2017 Google LLC
 * SPDX-License-Identifier: BSD-3-Clause
 */function ht(t){return lt({...t,state:!0,attribute:!1})}var pt;!function(t){t[t.Duration=0]="Duration",t[t.Volume=1]="Volume"}(pt||(pt={}));const ut=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];let mt=class extends nt{constructor(){super(...arguments),this._timers=new Map,this._editing=null,this._isNew=!1}setConfig(t){if(!t.entity)throw new Error("Please define an entity (timer registry sensor)");if(!t.device_id)throw new Error("Please define a device_id");this._config=t}getCardSize(){return 4}updated(t){t.has("hass")&&this.hass&&this._updateTimersFromState()}_updateTimersFromState(){const t=this.hass.states[this._config.entity];if(!t)return;const e=t.attributes?.slots;if(!e)return;const i=new Map;for(let t=0;t<7;t++){const s=e[String(t)];s&&i.set(t,{slot:t,mode:"volume"===s.mode?pt.Volume:pt.Duration,value:s.value,hour:s.hour,minute:s.minute,daysMask:s.days_mask,enabled:s.enabled})}this._timers=i}_newTimer(){for(let t=0;t<7;t++)if(!this._timers.has(t))return{slot:t,mode:pt.Duration,value:900,hour:6,minute:0,daysMask:127,enabled:!0};return{slot:0,mode:pt.Duration,value:900,hour:6,minute:0,daysMask:127,enabled:!0}}async _sendSetTimer(t){await this.hass.callService("xtend_tuya","fdm5kw_set_timer",{device_id:this._config.device_id,slot:t.slot,hour:t.hour,minute:t.minute,mode:t.mode===pt.Volume?"volume":"duration",value:t.value,days:t.daysMask,enabled:t.enabled})}async _sendDeleteTimer(t){await this.hass.callService("xtend_tuya","fdm5kw_delete_timer",{device_id:this._config.device_id,slot:t})}async _saveTimer(){this._editing&&(await this._sendSetTimer(this._editing),this._timers=new Map(this._timers),this._timers.set(this._editing.slot,{...this._editing}),this._editing=null,this._isNew=!1)}async _deleteTimer(t){await this._sendDeleteTimer(t),this._timers=new Map(this._timers),this._timers.delete(t)}_startEdit(t){this._editing={...t},this._isNew=!1}_startNew(){this._editing=this._newTimer(),this._isNew=!0}_cancelEdit(){this._editing=null,this._isNew=!1}render(){if(!this._config||!this.hass)return W;const t=this.hass.states[this._config.entity]?.attributes,e=t?.valve_name,i=this._config.name??e??t?.friendly_name??"Irrigation Timer";return V`
      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:timer-cog-outline"></ha-icon>
          <span>${i}</span>
        </div>
        <div class="card-content">
          ${this._editing?this._renderEditor():this._renderList()}
        </div>
      </ha-card>
    `}_renderList(){const t=Array.from(this._timers.values()).sort((t,e)=>t.slot-e.slot);return V`
      ${0===t.length?V`<div class="empty">No timers configured</div>`:t.map(t=>this._renderTimerRow(t))}
      <button class="add-btn" @click=${this._startNew}>
        <ha-icon icon="mdi:plus"></ha-icon>
        Add Timer
      </button>
    `}_renderTimerRow(t){const e=`${t.hour.toString().padStart(2,"0")}:${t.minute.toString().padStart(2,"0")}`,i=t.mode===pt.Duration?`${Math.floor(t.value/60)}min`:`${t.value}L`,s=ut.filter((e,i)=>t.daysMask&1<<i).join(", ");return V`
      <div class="timer-row ${t.enabled?"":"disabled"}">
        <div class="timer-info" @click=${()=>this._startEdit(t)}>
          <div class="timer-time">${e}</div>
          <div class="timer-details">
            <span class="timer-value">${i}</span>
            <span class="timer-days">${s}</span>
          </div>
        </div>
        <div class="timer-actions">
          <ha-switch
            .checked=${t.enabled}
            @change=${e=>this._toggleEnabled(t,e)}
          ></ha-switch>
        </div>
      </div>
    `}async _toggleEnabled(t,e){const i=e.target.checked,s={...t,enabled:i};await this._sendSetTimer(s),this._timers=new Map(this._timers),this._timers.set(t.slot,s)}_renderEditor(){const t=this._editing;return V`
      <div class="editor">
        <div class="editor-row">
          <label>Time</label>
          <input
            type="time"
            .value=${`${t.hour.toString().padStart(2,"0")}:${t.minute.toString().padStart(2,"0")}`}
            @change=${e=>{const[i,s]=e.target.value.split(":");this._editing={...t,hour:parseInt(i,10),minute:parseInt(s,10)}}}
          />
        </div>

        <div class="editor-row">
          <label>Mode</label>
          <div class="mode-toggle">
            <button
              class=${t.mode===pt.Duration?"active":""}
              @click=${()=>{this._editing={...t,mode:pt.Duration,value:t.mode===pt.Volume?900:t.value}}}
            >
              <ha-icon icon="mdi:timer-outline"></ha-icon>
              Duration
            </button>
            <button
              class=${t.mode===pt.Volume?"active":""}
              @click=${()=>{this._editing={...t,mode:pt.Volume,value:t.mode===pt.Duration?50:t.value}}}
            >
              <ha-icon icon="mdi:water"></ha-icon>
              Volume
            </button>
          </div>
        </div>

        <div class="editor-row">
          <label>${t.mode===pt.Duration?"Duration (min)":"Volume (L)"}</label>
          <input
            type="number"
            min="1"
            max=${t.mode===pt.Duration?1440:9999}
            .value=${t.mode===pt.Duration?Math.floor(t.value/60):t.value}
            @change=${e=>{const i=parseInt(e.target.value,10);this._editing={...t,value:t.mode===pt.Duration?60*i:i}}}
          />
        </div>

        <div class="editor-row">
          <label>Days</label>
          <div class="day-picker">
            ${ut.map((e,i)=>V`
                <button
                  class="day-btn ${t.daysMask&1<<i?"active":""}"
                  @click=${()=>{this._editing={...t,daysMask:t.daysMask^1<<i}}}
                >
                  ${e.charAt(0)}${e.charAt(1)}
                </button>
              `)}
          </div>
        </div>

        <div class="editor-actions">
          ${this._isNew?W:V`<button
                class="delete-btn"
                @click=${()=>{this._deleteTimer(t.slot),this._editing=null,this._isNew=!1}}
              >
                Delete
              </button>`}
          <button class="cancel-btn" @click=${this._cancelEdit}>
            Cancel
          </button>
          <button class="save-btn" @click=${this._saveTimer}>Save</button>
        </div>
      </div>
    `}};mt.styles=((t,...e)=>{const i=1===t.length?t[0]:e.reduce((e,i,s)=>e+(t=>{if(!0===t._$cssResult$)return t.cssText;if("number"==typeof t)return t;throw Error("Value passed to 'css' function must be a 'css' function result: "+t+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(i)+t[s+1],t[0]);return new o(i,t,s)})`
    :host {
      --timer-card-primary: var(--primary-color, #03a9f4);
      --timer-card-bg: var(--card-background-color, #fff);
      --timer-card-text: var(--primary-text-color, #212121);
      --timer-card-secondary: var(--secondary-text-color, #727272);
      --timer-card-disabled: var(--disabled-text-color, #bdbdbd);
      --timer-card-divider: var(--divider-color, #e0e0e0);
    }

    .card-header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px 16px 0;
      font-size: 1.1em;
      font-weight: 500;
      color: var(--timer-card-text);
    }

    .card-header ha-icon {
      color: var(--timer-card-primary);
    }

    .card-content {
      padding: 16px;
    }

    .empty {
      text-align: center;
      color: var(--timer-card-secondary);
      padding: 24px 0;
    }

    /* Timer list */
    .timer-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 0;
      border-bottom: 1px solid var(--timer-card-divider);
      cursor: pointer;
    }

    .timer-row:last-of-type {
      border-bottom: none;
    }

    .timer-row.disabled {
      opacity: 0.5;
    }

    .timer-info {
      flex: 1;
    }

    .timer-time {
      font-size: 1.5em;
      font-weight: 500;
      color: var(--timer-card-text);
      font-variant-numeric: tabular-nums;
    }

    .timer-details {
      display: flex;
      gap: 8px;
      color: var(--timer-card-secondary);
      font-size: 0.9em;
      margin-top: 2px;
    }

    .timer-value {
      font-weight: 500;
      color: var(--timer-card-primary);
    }

    .add-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      padding: 12px;
      margin-top: 8px;
      border: 2px dashed var(--timer-card-divider);
      border-radius: 8px;
      background: transparent;
      color: var(--timer-card-primary);
      font-size: 0.95em;
      cursor: pointer;
      transition: border-color 0.2s;
    }

    .add-btn:hover {
      border-color: var(--timer-card-primary);
    }

    /* Editor */
    .editor {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .editor-row {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .editor-row label {
      font-size: 0.85em;
      font-weight: 500;
      color: var(--timer-card-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .editor-row input[type="time"],
    .editor-row input[type="number"] {
      padding: 10px 12px;
      border: 1px solid var(--timer-card-divider);
      border-radius: 8px;
      background: var(--timer-card-bg);
      color: var(--timer-card-text);
      font-size: 1.1em;
      outline: none;
    }

    .editor-row input:focus {
      border-color: var(--timer-card-primary);
    }

    /* Mode toggle */
    .mode-toggle {
      display: flex;
      gap: 8px;
    }

    .mode-toggle button {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 10px;
      border: 1px solid var(--timer-card-divider);
      border-radius: 8px;
      background: transparent;
      color: var(--timer-card-secondary);
      font-size: 0.9em;
      cursor: pointer;
      transition: all 0.2s;
    }

    .mode-toggle button.active {
      background: var(--timer-card-primary);
      color: white;
      border-color: var(--timer-card-primary);
    }

    /* Day picker */
    .day-picker {
      display: flex;
      gap: 4px;
    }

    .day-btn {
      flex: 1;
      padding: 8px 0;
      border: 1px solid var(--timer-card-divider);
      border-radius: 8px;
      background: transparent;
      color: var(--timer-card-secondary);
      font-size: 0.8em;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;
    }

    .day-btn.active {
      background: var(--timer-card-primary);
      color: white;
      border-color: var(--timer-card-primary);
    }

    /* Editor actions */
    .editor-actions {
      display: flex;
      gap: 8px;
      margin-top: 8px;
    }

    .editor-actions button {
      flex: 1;
      padding: 10px;
      border: none;
      border-radius: 8px;
      font-size: 0.95em;
      font-weight: 500;
      cursor: pointer;
      transition: opacity 0.2s;
    }

    .save-btn {
      background: var(--timer-card-primary);
      color: white;
    }

    .cancel-btn {
      background: var(--timer-card-divider);
      color: var(--timer-card-text);
    }

    .delete-btn {
      background: var(--error-color, #db4437);
      color: white;
    }

    .editor-actions button:hover {
      opacity: 0.85;
    }
  `,t([lt({attribute:!1})],mt.prototype,"hass",void 0),t([ht()],mt.prototype,"_config",void 0),t([ht()],mt.prototype,"_timers",void 0),t([ht()],mt.prototype,"_editing",void 0),t([ht()],mt.prototype,"_isNew",void 0),mt=t([(t=>(e,i)=>{void 0!==i?i.addInitializer(()=>{customElements.define(t,e)}):customElements.define(t,e)})("irrigation-timer-card")],mt),window.customCards=window.customCards||[],window.customCards.push({type:"irrigation-timer-card",name:"Irrigation Timer",description:"Manage Tuya irrigation valve timer schedules"});export{mt as IrrigationTimerCard};
