interface PieceAvatarProps {
  pieceType: string
  color?: 'white' | 'black'
  size?: 'sm' | 'md' | 'lg'
  isTalking?: boolean
}

// Standard chess piece SVG paths (simplified outlines)
const pieceSvgs: Record<string, (fill: string, stroke: string) => JSX.Element> = {
  king: (fill, stroke) => (
    <svg viewBox="0 0 45 45" className="w-full h-full">
      <g fill={fill} stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M 22.5,11.63 L 22.5,6" strokeLinejoin="miter" />
        <path d="M 20,8 L 25,8" strokeLinejoin="miter" />
        <path d="M 22.5,25 C 22.5,25 27,17.5 25.5,14.5 C 25.5,14.5 24.5,12 22.5,12 C 20.5,12 19.5,14.5 19.5,14.5 C 18,17.5 22.5,25 22.5,25" />
        <path d="M 12.5,37 C 18,40.5 27,40.5 32.5,37 L 32.5,30 C 32.5,30 41.5,25.5 38.5,19.5 C 34.5,13 25,16 22.5,23.5 L 22.5,27 L 22.5,23.5 C 20,16 10.5,13 6.5,19.5 C 3.5,25.5 12.5,30 12.5,30 L 12.5,37" />
        <path d="M 12.5,30 C 18,27 27,27 32.5,30" />
        <path d="M 12.5,33.5 C 18,30.5 27,30.5 32.5,33.5" />
        <path d="M 12.5,37 C 18,34 27,34 32.5,37" />
      </g>
    </svg>
  ),
  queen: (fill, stroke) => (
    <svg viewBox="0 0 45 45" className="w-full h-full">
      <g fill={fill} stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M 9,26 C 17.5,24.5 30,24.5 36,26 L 38.5,13.5 L 31,25 L 30.7,10.9 L 25.5,24.5 L 22.5,10 L 19.5,24.5 L 14.3,10.9 L 14,25 L 6.5,13.5 L 9,26 z" />
        <path d="M 9,26 C 9,28 10.5,28.5 12.5,30 C 14.5,31.5 16.5,31 16.5,31 C 18.5,30 19.5,30 22.5,30 C 25.5,30 26.5,30 28.5,31 C 28.5,31 30.5,31.5 32.5,30 C 34.5,28.5 36,28 36,26" />
        <path d="M 9,26 C 9,28 12.5,31 12.5,31 L 12.5,37 C 18,40.5 27,40.5 32.5,37 L 32.5,31 C 32.5,31 36,28 36,26" fill="none" />
        <circle cx="6" cy="12" r="2.5" />
        <circle cx="14" cy="9" r="2.5" />
        <circle cx="22.5" cy="8" r="2.5" />
        <circle cx="31" cy="9" r="2.5" />
        <circle cx="39" cy="12" r="2.5" />
        <path d="M 12.5,30 C 18,27 27,27 32.5,30" fill="none" />
        <path d="M 12.5,33.5 C 18,30.5 27,30.5 32.5,33.5" fill="none" />
        <path d="M 12.5,37 C 18,34 27,34 32.5,37" fill="none" />
      </g>
    </svg>
  ),
  rook: (fill, stroke) => (
    <svg viewBox="0 0 45 45" className="w-full h-full">
      <g fill={fill} stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M 9,39 L 36,39 L 36,36 L 9,36 L 9,39 z" />
        <path d="M 12.5,32 L 14,29.5 L 31,29.5 L 32.5,32 L 12.5,32 z" />
        <path d="M 12,36 L 12,32 L 33,32 L 33,36 L 12,36 z" />
        <path d="M 14,29.5 L 14,16.5 L 31,16.5 L 31,29.5 L 14,29.5 z" />
        <path d="M 14,16.5 L 11,14 L 34,14 L 31,16.5 L 14,16.5 z" />
        <path d="M 11,14 L 11,9 L 15,9 L 15,11 L 20,11 L 20,9 L 25,9 L 25,11 L 30,11 L 30,9 L 34,9 L 34,14 L 11,14 z" />
        <path d="M 12,35.5 L 33,35.5 L 33,35.5" fill="none" strokeWidth="1" />
        <path d="M 13,31.5 L 32,31.5" fill="none" strokeWidth="1" />
        <path d="M 14,29.5 L 31,29.5" fill="none" strokeWidth="1" />
        <path d="M 14,16.5 L 31,16.5" fill="none" strokeWidth="1" />
        <path d="M 11,14 L 34,14" fill="none" strokeWidth="1" />
      </g>
    </svg>
  ),
  bishop: (fill, stroke) => (
    <svg viewBox="0 0 45 45" className="w-full h-full">
      <g fill={fill} stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <g>
          <path d="M 9,36 C 12.4,35.7 19,36.4 22.5,34 C 26,36.4 32.6,35.7 36,36 C 36,36 37.7,36.8 39,38 C 38.3,38.9 37.4,38.9 36,38.5 C 32.6,37.6 26,38.3 22.5,37 C 19,38.3 12.4,37.6 9,38.5 C 7.6,38.9 6.7,38.9 6,38 C 7.3,36.8 9,36 9,36 z" />
          <path d="M 15,32 C 17.5,34.5 27.5,34.5 30,32 C 30.5,30.5 30,30 30,30 C 30,27.5 27.5,26 27.5,26 C 33,24.5 33.5,14.5 22.5,10.5 C 11.5,14.5 12,24.5 17.5,26 C 17.5,26 15,27.5 15,30 C 15,30 14.5,30.5 15,32 z" />
          <path d="M 25,8 A 2.5,2.5 0 1 1 20,8 A 2.5,2.5 0 1 1 25,8 z" />
        </g>
        <path d="M 17.5,26 L 27.5,26 M 15,30 L 30,30 M 22.5,15.5 L 22.5,20.5" fill="none" strokeLinejoin="miter" />
      </g>
    </svg>
  ),
  knight: (fill, stroke) => (
    <svg viewBox="0 0 45 45" className="w-full h-full">
      <g fill={fill} stroke={stroke} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M 22,10 C 32.5,11 38.5,18 38,39 L 15,39 C 15,30 25,32.5 23,18" />
        <path d="M 24,18 C 24.38,20.91 18.45,25.37 16,27 C 13,29 13.18,31.34 11,31 C 9.958,30.06 12.41,27.96 11,28 C 10,28 11.19,29.23 10,30 C 9,30 5.997,31 6,26 C 6,24 12,14 12,14 C 12,14 13.89,12.1 14,10.5 C 13.27,9.506 13.5,8.5 13.5,7.5 C 14.5,6.5 16.5,10 16.5,10 L 18.5,10 C 18.5,10 19.28,8.008 21,7 C 22,7 22,10 22,10" />
        <path d="M 9.5,25.5 A 0.5,0.5 0 1 1 8.5,25.5 A 0.5,0.5 0 1 1 9.5,25.5 z" fill={stroke} stroke={stroke} />
        <path d="M 15,15.5 A 0.5,1.5 0 1 1 14,15.5 A 0.5,1.5 0 1 1 15,15.5 z" fill={stroke} stroke={stroke} transform="matrix(0.866,0.5,-0.5,0.866,9.693,-5.173)" />
      </g>
    </svg>
  ),
  pawn: (fill, stroke) => (
    <svg viewBox="0 0 45 45" className="w-full h-full">
      <path d="M 22.5,9 C 19.79,9 17.609,11.18 17.609,13.89 C 17.609,15.05 18.05,16.1 18.78,16.89 C 16.29,18.35 14.609,21.07 14.609,24.18 C 14.609,26.09 15.24,27.85 16.31,29.27 C 13.55,30.55 11.609,33.35 11.609,36.61 L 33.39,36.61 C 33.39,33.35 31.45,30.55 28.69,29.27 C 29.76,27.85 30.39,26.09 30.39,24.18 C 30.39,21.07 28.71,18.35 26.22,16.89 C 26.95,16.1 27.39,15.05 27.39,13.89 C 27.39,11.18 25.21,9 22.5,9 z" fill={fill} stroke={stroke} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  ),
}

const sizeClasses = {
  sm: 'w-8 h-8',
  md: 'w-12 h-12',
  lg: 'w-16 h-16',
}

export function PieceAvatar({ pieceType, color = 'white', size = 'md', isTalking = false }: PieceAvatarProps) {
  const type = pieceType.toLowerCase()
  const renderPiece = pieceSvgs[type]

  const fill = color === 'white' ? '#ffffff' : '#1a1a2e'
  const stroke = color === 'white' ? '#333333' : '#cccccc'
  const bgGradient = color === 'white'
    ? 'from-amber-100 to-amber-200'
    : 'from-slate-600 to-slate-700'
  const borderColor = color === 'white'
    ? 'border-amber-300'
    : 'border-slate-500'

  return (
    <div
      className={`
        ${sizeClasses[size]}
        rounded-full
        bg-gradient-to-br ${bgGradient}
        ${borderColor} border-2
        flex items-center justify-center
        p-1
        shadow-lg
        flex-shrink-0
        ${isTalking ? 'ring-2 ring-blue-400 ring-offset-2 ring-offset-slate-800 animate-pulse' : ''}
      `}
    >
      {renderPiece ? (
        <div className="w-full h-full">
          {renderPiece(fill, stroke)}
        </div>
      ) : (
        <span className={`${size === 'lg' ? 'text-2xl' : size === 'md' ? 'text-xl' : 'text-sm'} leading-none`}>
          {type === 'supervisor' ? '\uD83D\uDC54' : '\uD83E\uDD16'}
        </span>
      )}
    </div>
  )
}

export function getSupervisorAvatar(size: 'sm' | 'md' | 'lg' = 'md') {
  return (
    <div
      className={`
        ${sizeClasses[size]}
        rounded-full
        bg-gradient-to-br from-indigo-500 to-purple-600
        border-2 border-indigo-400
        flex items-center justify-center
        shadow-lg
        flex-shrink-0
      `}
    >
      <span className={`${size === 'lg' ? 'text-2xl' : size === 'md' ? 'text-lg' : 'text-sm'} leading-none`}>
        {'\u265A'}
      </span>
    </div>
  )
}
