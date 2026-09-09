(function(){
  "use strict";

  /* ══════════════ живой граф транзакций ══════════════ */
  var cv=document.getElementById('topo'), ctx=cv.getContext('2d');
  var W=0,H=0,DPR=Math.min(window.devicePixelRatio||1,2);

  var C={line:'#C9D2DA',dim:'#778394',accent:'#1B5B66',fraud:'#A8261F',exit:'#B4741C',
         honest:'#2C6E52',surf:'#FFFFFF',ground:'#FFFFFF'};

  var CAPS={
    LEGAL_LAYERING:'Каскад посредников: сумма идёт слоями, на каждом слое дробясь.',
    LEGAL_TO_CRYPTO_BRIDGE:'Фиатные счета сходятся к шлюзу и уходят в криптоадреса.',
    CRYPTO_MIXING:'Миксер: входы перемешиваются и выходят другим составом.',
    STRUCTURED_SPLITTING:'Дробление под пороги: крупная сумма расходится веером и собирается снова.',
    CASH_OUT:'Банкоматная вспышка: десятки веток сходятся к паре ATM за 15 минут.'
  };

  var nodes=[],edges=[],pulses=[],current='LEGAL_LAYERING';

  function N(x,y,r,kind){return{x:x,y:y,vx:0,vy:0,r:r,kind:kind};}

  function build(t){
    nodes=[];edges=[];pulses=[];
    var i,j,k,src,mid,gate,out,layer,prev;
    function link(a,b){edges.push([a,b]);}

    if(t==='LEGAL_LAYERING'){
      src=[];for(i=0;i<7;i++){src.push(nodes.push(N(.10,(i+1)/8,4,'src'))-1);}
      prev=src;
      for(layer=0;layer<3;layer++){
        var cur=[];var cnt=[5,3,2][layer];
        for(i=0;i<cnt;i++){cur.push(nodes.push(N(.30+layer*.19,(i+1)/(cnt+1),5,'mid'))-1);}
        for(i=0;i<prev.length;i++)for(j=0;j<cur.length;j++)if((i+j)%2===0)link(prev[i],cur[j]);
        prev=cur;
      }
      out=nodes.push(N(.90,.5,9,'exit'))-1;
      for(i=0;i<prev.length;i++)link(prev[i],out);
    }

    else if(t==='LEGAL_TO_CRYPTO_BRIDGE'){
      src=[];for(i=0;i<8;i++){src.push(nodes.push(N(.10,(i+1)/9,4,'src'))-1);}
      gate=nodes.push(N(.46,.5,10,'fraud'))-1;
      for(i=0;i<src.length;i++)link(src[i],gate);
      var addr=[];for(i=0;i<6;i++){addr.push(nodes.push(N(.76,(i+1)/7,5,'crypto'))-1);link(gate,addr[i]);}
      out=nodes.push(N(.94,.5,8,'exit'))-1;
      for(i=0;i<addr.length;i+=2)link(addr[i],out);
    }

    else if(t==='CRYPTO_MIXING'){
      src=[];for(i=0;i<5;i++){src.push(nodes.push(N(.12,(i+1)/6,4.5,'src'))-1);}
      mid=[];for(i=0;i<6;i++){mid.push(nodes.push(N(.42+(i%2)*.16,(i+1)/7,5,'fraud'))-1);}
      for(i=0;i<src.length;i++)for(j=0;j<mid.length;j++)if((i*j+i+j)%3===0)link(src[i],mid[j]);
      for(i=0;i<mid.length;i++)for(j=0;j<mid.length;j++)if(i!==j&&(i+j)%4===0)link(mid[i],mid[j]);
      var o2=[];for(i=0;i<4;i++){o2.push(nodes.push(N(.88,(i+1)/5,5,'exit'))-1);}
      for(i=0;i<mid.length;i++)link(mid[i],o2[i%o2.length]);
    }

    else if(t==='STRUCTURED_SPLITTING'){
      var head=nodes.push(N(.10,.5,10,'fraud'))-1;
      mid=[];for(i=0;i<9;i++){mid.push(nodes.push(N(.48,(i+1)/10,4,'mid'))-1);link(head,mid[i]);}
      out=nodes.push(N(.90,.5,10,'exit'))-1;
      for(i=0;i<mid.length;i++)link(mid[i],out);
    }

    else{ /* CASH_OUT */
      src=[];for(i=0;i<12;i++){src.push(nodes.push(N(.10,(i+1)/13,3.6,'src'))-1);}
      mid=[];for(i=0;i<4;i++){mid.push(nodes.push(N(.44,(i+1)/5,5.5,'mid'))-1);}
      for(i=0;i<src.length;i++)link(src[i],mid[i%mid.length]);
      var atm=[];for(i=0;i<2;i++){atm.push(nodes.push(N(.86,(i+1)/3,11,'atm'))-1);}
      for(i=0;i<mid.length;i++)for(j=0;j<atm.length;j++)link(mid[i],atm[j]);
    }

    for(k=0;k<edges.length;k++)pulses.push(Math.random());
    document.getElementById('tn').textContent=nodes.length;
    document.getElementById('te').textContent=edges.length;
    document.getElementById('tcap').textContent=CAPS[t];
  }

  function colorOf(kind){
    if(kind==='fraud'||kind==='atm')return C.fraud;
    if(kind==='exit')return C.exit;
    if(kind==='crypto')return C.accent;
    if(kind==='mid')return C.accent;
    return C.dim;
  }

  function resize(){
    var r=cv.getBoundingClientRect();
    W=r.width;H=r.height;
    cv.width=Math.round(W*DPR);cv.height=Math.round(H*DPR);
    ctx.setTransform(DPR,0,0,DPR,0,0);
  }

  var reduce=window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function draw(t){
    ctx.clearRect(0,0,W,H);
    var pad=26,i,e,a,b,ax,ay,bx,by;

    function px(n){return pad+n.x*(W-pad*2);}
    function py(n){return pad+n.y*(H-pad*2);}

    /* рёбра */
    for(i=0;i<edges.length;i++){
      e=edges[i];a=nodes[e[0]];b=nodes[e[1]];
      ax=px(a);ay=py(a);bx=px(b);by=py(b);
      ctx.beginPath();ctx.moveTo(ax,ay);ctx.lineTo(bx,by);
      ctx.strokeStyle=C.line;ctx.lineWidth=1;ctx.stroke();
    }
    /* импульсы денег */
    if(!reduce){
      for(i=0;i<edges.length;i++){
        e=edges[i];a=nodes[e[0]];b=nodes[e[1]];
        pulses[i]+=0.0042+(i%5)*0.0006;
        if(pulses[i]>1)pulses[i]-=1;
        var p=pulses[i];
        ax=px(a);ay=py(a);bx=px(b);by=py(b);
        var cx=ax+(bx-ax)*p, cy=ay+(by-ay)*p;
        var col=colorOf(nodes[e[1]].kind);
        ctx.beginPath();ctx.arc(cx,cy,1.9,0,6.2832);
        ctx.fillStyle=col;ctx.globalAlpha=.85;ctx.fill();ctx.globalAlpha=1;
      }
    }
    /* вершины */
    for(i=0;i<nodes.length;i++){
      var n=nodes[i],x=px(n),y=py(n),col=colorOf(n.kind);
      if(n.kind==='atm'){
        ctx.beginPath();ctx.rect(x-n.r,y-n.r*.8,n.r*2,n.r*1.6);
        ctx.fillStyle=C.surf;ctx.fill();ctx.strokeStyle=col;ctx.lineWidth=1.6;ctx.stroke();
        ctx.fillStyle=col;ctx.font='600 8px IBM Plex Mono, monospace';ctx.textAlign='center';
        ctx.fillText('ATM',x,y+3);
      }else{
        if(n.kind==='fraud'||n.kind==='exit'){
          ctx.beginPath();ctx.arc(x,y,n.r+5,0,6.2832);
          ctx.fillStyle=col;ctx.globalAlpha=.10;ctx.fill();ctx.globalAlpha=1;
        }
        ctx.beginPath();ctx.arc(x,y,n.r,0,6.2832);
        ctx.fillStyle=C.surf;ctx.fill();
        ctx.strokeStyle=col;ctx.lineWidth=n.kind==='src'?1:1.6;ctx.stroke();
      }
    }
    if(!reduce)requestAnimationFrame(draw);
  }

  var btns=[].slice.call(document.querySelectorAll('.topo-bar button'));
  btns.forEach(function(b){
    b.addEventListener('click',function(){
      btns.forEach(function(o){o.setAttribute('aria-pressed',String(o===b));});
      current=b.dataset.t;build(current);
    });
  });

  window.addEventListener('resize',function(){resize();});
  resize();build(current);
  if(reduce){draw(0);}else{requestAnimationFrame(draw);}

  /* ══════════════ параметр W ══════════════ */
  /* Сценарии: пары (объём исходящей посылки, Δt в условных сутках) при V_in = 100. */
  var SCEN=[
    {pairs:[[20,3.0],[15,4.0]]},   /* обычный клиент  */
    {pairs:[[45,1.2],[25,2.0]]},   /* пирамида        */
    {pairs:[[60,0.05],[38,0.15]]}  /* дроппер         */
  ];
  var lam=document.getElementById('lam'), lamv=document.getElementById('lamv'),
      wnote=document.getElementById('wnote');

  function recompute(){
    var L=parseInt(lam.value,10)/100;
    lamv.textContent=L.toFixed(2);
    var vals=SCEN.map(function(s){
      var sum=0;
      for(var i=0;i<s.pairs.length;i++)sum+=s.pairs[i][0]*Math.exp(-L*s.pairs[i][1]);
      return sum/100;
    });
    for(var i=0;i<3;i++){
      document.querySelector('[data-s="'+i+'"]').style.width=(vals[i]*100).toFixed(1)+'%';
      document.querySelector('[data-v="'+i+'"]').textContent=vals[i].toFixed(2);
    }
    var gap=vals[2]-vals[0];
    wnote.textContent='При λ = '+L.toFixed(2)+' разрыв между честным клиентом и дроппером составляет '
      +gap.toFixed(2)+'. Малые λ растягивают память системы на месяцы и настраивают её на пирамиды, '
      +'большие сжимают до минут и ловят скоростной вывод.';
  }
  lam.addEventListener('input',recompute);
  recompute();
})();
