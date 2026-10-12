import React, {useEffect, useId, useRef, useState} from 'react';
import {Check, ChevronDown} from 'lucide-react';
import {createPortal} from 'react-dom';
import './StyledSelect.css';

export default function StyledSelect({value, onChange, options: suppliedOptions, children, label, disabled, className='', ...rest}) {
  const options=suppliedOptions || React.Children.toArray(children).filter(React.isValidElement).map(child=>({value:child.props.value ?? child.props.children,label:child.props.children,disabled:child.props.disabled}));
  const id=useId(), root=useRef(null), menu=useRef(null), trigger=useRef(null);
  const [position,setPosition]=useState({});
  const [open,setOpen]=useState(false), [active,setActive]=useState(0);
  const selected=options.findIndex(option=>String(option.value)===String(value));
  useEffect(()=>{
    if(!open)return;
    const close=e=>{if(!root.current?.contains(e.target) && !menu.current?.contains(e.target))setOpen(false);};
    const place=()=>{const rect=trigger.current.getBoundingClientRect();const below=window.innerHeight-rect.bottom-16;const above=below<160 && rect.top>below;const height=Math.min(280,Math.max(80,above?rect.top-16:below));setPosition({left:rect.left,width:rect.width,maxHeight:height,...(above?{bottom:window.innerHeight-rect.top+7,top:'auto'}:{top:rect.bottom+7,bottom:'auto'})});};
    place();
    document.addEventListener('pointerdown',close);
    window.addEventListener('resize',place);window.addEventListener('scroll',place,true);
    return ()=>{document.removeEventListener('pointerdown',close);window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
  },[open]);
  useEffect(()=>{if(open)document.getElementById(id+'-'+active)?.scrollIntoView({block:'nearest'});},[open,active,id]);
  function choose(index){if(!options[index] || options[index].disabled || disabled || trigger.current?.matches(':disabled'))return;const next=String(options[index].value);onChange(suppliedOptions?options[index].value:{target:{value:next},currentTarget:{value:next}});setOpen(false);}
  function keyDown(e){
    if(e.key==='Escape'){setOpen(false);return;}
    if(e.key==='Tab'){setOpen(false);return;}
    if(['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(e.key)){
      e.preventDefault();
      if(!open){setActive(Math.max(0,selected));setOpen(true);return;}
      if(e.key==='Enter'||e.key===' '){choose(active);return;}
      setActive(index=>e.key==='Home'?0:e.key==='End'?options.length-1:Math.max(0,Math.min(options.length-1,index+(e.key==='ArrowDown'?1:-1))));
    }
  }
  return <div className={'styled-select '+className} ref={root} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setOpen(false);}}>
    <button {...rest} ref={trigger} disabled={disabled} type="button" className="styled-select-trigger" role="combobox" aria-label={label || rest['aria-label']} aria-expanded={open} aria-controls={id} aria-haspopup="listbox" aria-activedescendant={open?id+'-'+active:undefined} onKeyDown={keyDown} onClick={()=>{setActive(Math.max(0,selected));setOpen(!open);}}>
      <span>{options[selected]?.label || 'Выберите вариант'}</span><ChevronDown size={17} className={open?'turned':''}/>
    </button>
    {open && createPortal(<div ref={menu} className="styled-select-menu" style={position} id={id} role="listbox" aria-label={label || rest['aria-label']}>
      {options.map((option,index)=><div className={'styled-select-option'+(index===active?' highlighted':'')} key={option.value} id={id+'-'+index} role="option" aria-disabled={Boolean(option.disabled)} aria-selected={index===selected} onPointerMove={()=>setActive(index)} onMouseDown={e=>e.preventDefault()} onClick={e=>{e.preventDefault();e.stopPropagation();choose(index);}}><span>{option.label}</span>{index===selected && <Check size={16}/>}</div>)}
    </div>,document.body)}
  </div>;
}
