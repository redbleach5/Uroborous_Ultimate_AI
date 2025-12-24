import React from 'react';

interface UroborosLogoProps {
  size?: number;
  className?: string;
}

export function UroborosLogo({ size = 32, className = '' }: UroborosLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        {/* Body gradient */}
        <linearGradient id="uroBodyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#60A5FA" />
          <stop offset="40%" stopColor="#818CF8" />
          <stop offset="100%" stopColor="#A78BFA" />
        </linearGradient>
        
        {/* Belly gradient */}
        <linearGradient id="uroBellyGrad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#C7D2FE" />
          <stop offset="100%" stopColor="#A5B4FC" />
        </linearGradient>
        
        {/* Head gradient */}
        <linearGradient id="uroHeadGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#818CF8" />
          <stop offset="100%" stopColor="#6366F1" />
        </linearGradient>
        
        {/* Glow filter */}
        <filter id="uroGlow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="1" result="blur"/>
          <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>
      
      {/* ===== SERPENT BODY - Spiral/curved path, NOT closed circle ===== */}
      <g filter="url(#uroGlow)">
        
        {/* Main body - curved serpentine shape */}
        <path
          d="M 36 8
             C 44 12, 46 22, 44 30
             C 42 38, 34 44, 26 44
             C 18 44, 10 38, 8 30
             C 6 22, 10 14, 16 10
             C 20 7, 26 6, 30 8"
          stroke="url(#uroBodyGrad)"
          strokeWidth="5"
          strokeLinecap="round"
          fill="none"
        />
        
        {/* Belly line - lighter inner curve */}
        <path
          d="M 35 10
             C 41 14, 43 22, 41 29
             C 39 36, 33 41, 26 41
             C 19 41, 13 36, 11 29
             C 9 22, 12 15, 17 12
             C 20 10, 25 9, 29 10"
          stroke="url(#uroBellyGrad)"
          strokeWidth="1.5"
          strokeLinecap="round"
          fill="none"
          opacity="0.6"
        />
        
        {/* ===== SCALES along the body ===== */}
        {/* Outer scales - detailed pattern */}
        <g opacity="0.8">
          {/* Top right curve */}
          <path d="M38 10 L40 8 L41 11" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
          <path d="M42 14 L44 12 L45 15" stroke="#A78BFA" strokeWidth="0.8" fill="none"/>
          <path d="M44 20 L47 19 L46 22" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
          <path d="M45 26 L48 26 L46 29" stroke="#A78BFA" strokeWidth="0.8" fill="none"/>
          <path d="M44 32 L47 33 L45 36" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
          
          {/* Bottom curve */}
          <path d="M40 38 L42 41 L39 41" stroke="#A78BFA" strokeWidth="0.8" fill="none"/>
          <path d="M34 42 L35 45 L32 44" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
          <path d="M27 44 L27 47 L24 45" stroke="#A78BFA" strokeWidth="0.8" fill="none"/>
          <path d="M20 43 L19 46 L17 43" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
          <path d="M14 40 L12 43 L11 40" stroke="#A78BFA" strokeWidth="0.8" fill="none"/>
          
          {/* Left curve */}
          <path d="M9 34 L6 35 L8 32" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
          <path d="M7 28 L4 28 L6 25" stroke="#A78BFA" strokeWidth="0.8" fill="none"/>
          <path d="M7 22 L4 21 L7 18" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
          <path d="M10 16 L7 14 L10 12" stroke="#A78BFA" strokeWidth="0.8" fill="none"/>
          <path d="M14 12 L12 9 L15 10" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
          
          {/* Near head */}
          <path d="M20 9 L19 6 L22 8" stroke="#A78BFA" strokeWidth="0.8" fill="none"/>
          <path d="M26 7 L26 4 L29 6" stroke="#93C5FD" strokeWidth="0.8" fill="none"/>
        </g>
        
        {/* ===== SPINE RIDGE - dorsal spines ===== */}
        <g opacity="0.7">
          <path d="M37 7 L39 4 L40 8" fill="#818CF8"/>
          <path d="M43 13 L46 11 L45 15" fill="#818CF8"/>
          <path d="M46 21 L49 20 L47 24" fill="#818CF8"/>
          <path d="M45 29 L48 29 L46 33" fill="#818CF8"/>
          <path d="M42 37 L44 40 L40 39" fill="#818CF8"/>
          <path d="M35 43 L36 46 L32 44" fill="#818CF8"/>
          <path d="M27 45 L26 48 L23 45" fill="#818CF8"/>
          <path d="M19 43 L17 46 L15 43" fill="#818CF8"/>
          <path d="M11 38 L8 40 L9 36" fill="#818CF8"/>
          <path d="M6 30 L3 31 L5 27" fill="#818CF8"/>
          <path d="M6 22 L3 21 L6 18" fill="#818CF8"/>
          <path d="M9 14 L6 12 L10 11" fill="#818CF8"/>
          <path d="M15 9 L14 6 L18 8" fill="#818CF8"/>
          <path d="M23 6 L24 3 L27 6" fill="#818CF8"/>
        </g>
      </g>
      
      {/* ===== DRAGON HEAD - detailed ===== */}
      <g>
        {/* Head base shape */}
        <ellipse
          cx="33"
          cy="8"
          rx="6"
          ry="4.5"
          fill="url(#uroHeadGrad)"
        />
        
        {/* Snout/muzzle */}
        <path
          d="M37 6 Q40 7, 40 9 Q40 11, 37 10 Z"
          fill="#6366F1"
        />
        
        {/* Upper jaw */}
        <path
          d="M28 6 C30 4, 36 4, 38 6 L37 7 C35 6, 31 6, 29 7 Z"
          fill="#818CF8"
        />
        
        {/* Lower jaw - holding tail */}
        <path
          d="M28 10 C30 12, 36 12, 38 10 L37 9 C35 10, 31 10, 29 9 Z"
          fill="#4F46E5"
        />
        
        {/* Eye left - detailed */}
        <ellipse cx="31" cy="7" rx="1.8" ry="1.2" fill="#1E1B4B"/>
        <ellipse cx="31" cy="7" rx="1.2" ry="0.8" fill="#312E81"/>
        <circle cx="31.5" cy="6.5" r="0.5" fill="#FEF3C7"/>
        <circle cx="30.5" cy="7.2" r="0.2" fill="#FEF3C7" opacity="0.6"/>
        
        {/* Eye ridge/brow */}
        <path d="M29 5.5 Q31 4.5, 33 5.5" stroke="#4338CA" strokeWidth="0.6" fill="none"/>
        
        {/* Nostril */}
        <ellipse cx="38" cy="7" rx="0.6" ry="0.4" fill="#312E81"/>
        
        {/* Teeth - sharp and visible */}
        <g fill="#E0E7FF">
          <path d="M30 9 L30.5 7.5 L31 9"/>
          <path d="M32 9 L32.5 7 L33 9"/>
          <path d="M34 9 L34.5 7.5 L35 9"/>
          <path d="M36 9 L36.3 8 L36.6 9"/>
        </g>
        
        {/* Horns */}
        <path
          d="M27 5 C25 3, 24 1, 26 0 C27 1, 28 3, 28 5"
          fill="#A78BFA"
          stroke="#818CF8"
          strokeWidth="0.3"
        />
        <path
          d="M29 4 C28 2, 28 0, 30 0 C30 1, 30 3, 30 4"
          fill="#C4B5FD"
          stroke="#A78BFA"
          strokeWidth="0.3"
        />
        
        {/* Ear/fin */}
        <path
          d="M26 8 C24 7, 23 9, 25 10"
          stroke="#818CF8"
          strokeWidth="0.8"
          fill="#6366F1"
        />
        
        {/* Head crest/ridge */}
        <path d="M28 5 L27 3 L29 4" fill="#A78BFA" opacity="0.8"/>
        <path d="M30 4 L30 2 L32 4" fill="#A78BFA" opacity="0.6"/>
      </g>
      
      {/* ===== TAIL being eaten ===== */}
      <g>
        {/* Tail end going into mouth */}
        <path
          d="M31 10 C32 12, 33 12, 34 10"
          stroke="url(#uroBodyGrad)"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />
        
        {/* Tail tip detail */}
        <path
          d="M32 11 L32.5 13 L33 11"
          fill="#93C5FD"
        />
        <path
          d="M31.5 11 L32 12.5 L32.5 11"
          fill="#60A5FA"
          opacity="0.7"
        />
        
        {/* Tail scales near mouth */}
        <circle cx="31" cy="10.5" r="0.4" fill="#A78BFA" opacity="0.6"/>
        <circle cx="34" cy="10.5" r="0.4" fill="#A78BFA" opacity="0.6"/>
      </g>
      
      {/* ===== BODY TEXTURE - cross-hatch pattern for scales ===== */}
      <g opacity="0.3" stroke="#C4B5FD" strokeWidth="0.3">
        {/* Subtle scale texture across body */}
        <path d="M42 18 C43 19, 43 20, 42 21"/>
        <path d="M43 24 C44 25, 44 26, 43 27"/>
        <path d="M41 32 C42 33, 42 34, 41 35"/>
        <path d="M36 40 C37 41, 36 42, 35 41"/>
        <path d="M28 43 C29 43, 29 44, 28 44"/>
        <path d="M20 42 C21 42, 21 43, 20 43"/>
        <path d="M13 38 C14 38, 14 39, 13 39"/>
        <path d="M9 32 C10 32, 10 33, 9 33"/>
        <path d="M8 25 C9 25, 9 26, 8 26"/>
        <path d="M10 18 C11 18, 11 19, 10 19"/>
        <path d="M15 13 C16 13, 16 14, 15 14"/>
        <path d="M22 10 C23 10, 23 11, 22 11"/>
      </g>
      
      {/* ===== HIGHLIGHT accents ===== */}
      <g opacity="0.4">
        <path 
          d="M40 12 C42 16, 43 20, 43 24" 
          stroke="#E0E7FF" 
          strokeWidth="1" 
          strokeLinecap="round"
          fill="none"
        />
        <path 
          d="M12 22 C11 26, 12 30, 14 34" 
          stroke="#E0E7FF" 
          strokeWidth="0.8" 
          strokeLinecap="round"
          fill="none"
        />
      </g>
    </svg>
  );
}

export default UroborosLogo;
