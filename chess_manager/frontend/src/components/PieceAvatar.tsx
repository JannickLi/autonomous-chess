interface PieceAvatarProps {
  pieceType: string
  color?: 'white' | 'black'
  size?: 'sm' | 'md' | 'lg'
  isTalking?: boolean
}

interface PieceCharacterProps {
  pieceType: string
  isSpeaking?: boolean
}

// Cartoon character SVGs — expressive, large, with personality
const characterSvgs: Record<string, (speaking: boolean) => JSX.Element> = {
  king: (speaking) => (
    <svg viewBox="0 0 128 128" className="w-full h-full">
      {/* Crown */}
      <polygon points="34,42 42,18 52,36 64,10 76,36 86,18 94,42" fill="#FFD700" stroke="#B8860B" strokeWidth="2" />
      <circle cx="64" cy="12" r="4" fill="#FF4444" />
      <circle cx="42" cy="20" r="3" fill="#4488FF" />
      <circle cx="86" cy="20" r="3" fill="#4488FF" />
      {/* Head */}
      <ellipse cx="64" cy="62" rx="28" ry="24" fill="#FFE0BD" stroke="#D4A574" strokeWidth="2" />
      {/* Eyes */}
      <ellipse cx="52" cy="56" rx="5" ry="6" fill="white" />
      <ellipse cx="76" cy="56" rx="5" ry="6" fill="white" />
      <circle cx="53" cy="57" r="3" fill="#2D1B00" />
      <circle cx="77" cy="57" r="3" fill="#2D1B00" />
      <circle cx="54" cy="55.5" r="1.2" fill="white" />
      <circle cx="78" cy="55.5" r="1.2" fill="white" />
      {/* Eyebrows — regal arch */}
      <path d="M 45,48 Q 52,43 59,48" fill="none" stroke="#5C3A1E" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M 69,48 Q 76,43 83,48" fill="none" stroke="#5C3A1E" strokeWidth="2.5" strokeLinecap="round" />
      {/* Mouth */}
      {speaking ? (
        <ellipse cx="64" cy="74" rx="8" ry="6" fill="#CC4444" stroke="#8B2020" strokeWidth="1.5">
          <animate attributeName="ry" values="6;4;6" dur="0.4s" repeatCount="indefinite" />
        </ellipse>
      ) : (
        <path d="M 56,72 Q 64,80 72,72" fill="none" stroke="#8B4513" strokeWidth="2" strokeLinecap="round" />
      )}
      {/* Mustache */}
      <path d="M 50,68 Q 57,72 64,68 Q 71,72 78,68" fill="none" stroke="#5C3A1E" strokeWidth="2.5" strokeLinecap="round" />
      {/* Body — regal robe */}
      <path d="M 36,86 Q 36,82 44,82 L 84,82 Q 92,82 92,86 L 96,116 L 32,116 Z" fill="#8B0000" stroke="#5C0000" strokeWidth="2" />
      <path d="M 56,82 L 56,116" stroke="#FFD700" strokeWidth="2" />
      <path d="M 72,82 L 72,116" stroke="#FFD700" strokeWidth="2" />
      {/* Collar */}
      <path d="M 44,82 Q 64,92 84,82" fill="#FFFFFF" stroke="#CCCCCC" strokeWidth="1.5" />
    </svg>
  ),
  queen: (speaking) => (
    <svg viewBox="0 0 128 128" className="w-full h-full">
      {/* Tiara */}
      <path d="M 38,44 L 44,26 L 54,38 L 64,20 L 74,38 L 84,26 L 90,44" fill="#C0C0C0" stroke="#888" strokeWidth="1.5" />
      <circle cx="64" cy="22" r="4" fill="#FF69B4" />
      <circle cx="44" cy="28" r="2.5" fill="#9B59B6" />
      <circle cx="84" cy="28" r="2.5" fill="#9B59B6" />
      {/* Head */}
      <ellipse cx="64" cy="60" rx="26" ry="22" fill="#FFE0BD" stroke="#D4A574" strokeWidth="2" />
      {/* Hair flowing */}
      <path d="M 38,52 Q 30,70 34,90" fill="none" stroke="#4A2810" strokeWidth="4" strokeLinecap="round" />
      <path d="M 90,52 Q 98,70 94,90" fill="none" stroke="#4A2810" strokeWidth="4" strokeLinecap="round" />
      {/* Eyes — elegant with lashes */}
      <ellipse cx="52" cy="56" rx="5" ry="5.5" fill="white" />
      <ellipse cx="76" cy="56" rx="5" ry="5.5" fill="white" />
      <circle cx="53" cy="57" r="3" fill="#1B5E20" />
      <circle cx="77" cy="57" r="3" fill="#1B5E20" />
      <circle cx="54" cy="55.5" r="1.2" fill="white" />
      <circle cx="78" cy="55.5" r="1.2" fill="white" />
      {/* Lashes */}
      <path d="M 46,52 L 44,49" stroke="#2D1B00" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M 48,50 L 47,47" stroke="#2D1B00" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M 82,52 L 84,49" stroke="#2D1B00" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M 80,50 L 81,47" stroke="#2D1B00" strokeWidth="1.5" strokeLinecap="round" />
      {/* Eyebrows */}
      <path d="M 45,49 Q 52,45 59,49" fill="none" stroke="#4A2810" strokeWidth="2" strokeLinecap="round" />
      <path d="M 69,49 Q 76,45 83,49" fill="none" stroke="#4A2810" strokeWidth="2" strokeLinecap="round" />
      {/* Mouth */}
      {speaking ? (
        <ellipse cx="64" cy="72" rx="7" ry="5" fill="#E74C3C" stroke="#C0392B" strokeWidth="1.5">
          <animate attributeName="ry" values="5;3;5" dur="0.35s" repeatCount="indefinite" />
        </ellipse>
      ) : (
        <path d="M 57,70 Q 64,77 71,70" fill="#E74C3C" stroke="#C0392B" strokeWidth="1.5" strokeLinecap="round" />
      )}
      {/* Body — elegant dress */}
      <path d="M 40,82 Q 64,78 88,82 L 98,118 Q 64,122 30,118 Z" fill="#9B59B6" stroke="#7D3C98" strokeWidth="2" />
      {/* Necklace */}
      <path d="M 44,82 Q 64,88 84,82" fill="none" stroke="#FFD700" strokeWidth="2" />
      <circle cx="64" cy="86" r="3" fill="#FF69B4" stroke="#FFD700" strokeWidth="1" />
    </svg>
  ),
  rook: (speaking) => (
    <svg viewBox="0 0 128 128" className="w-full h-full">
      {/* Battlement top */}
      <path d="M 36,36 L 36,22 L 46,22 L 46,30 L 54,30 L 54,22 L 64,22 L 64,30 L 74,30 L 74,22 L 84,22 L 84,30 L 92,30 L 92,22 L 92,36 Z" fill="#A0A0A0" stroke="#707070" strokeWidth="2" />
      {/* Head — blocky castle face */}
      <rect x="36" y="36" width="56" height="44" rx="6" fill="#C0C0C0" stroke="#888" strokeWidth="2" />
      {/* Eyes — stern, square-ish */}
      <rect x="46" y="48" width="10" height="10" rx="2" fill="white" />
      <rect x="72" y="48" width="10" height="10" rx="2" fill="white" />
      <rect x="49" y="51" width="5" height="5" rx="1" fill="#333" />
      <rect x="75" y="51" width="5" height="5" rx="1" fill="#333" />
      {/* Eyebrows — thick, no-nonsense */}
      <rect x="44" y="44" width="14" height="3" rx="1" fill="#555" />
      <rect x="70" y="44" width="14" height="3" rx="1" fill="#555" />
      {/* Mouth */}
      {speaking ? (
        <rect x="52" y="66" width="24" height="10" rx="4" fill="#666" stroke="#444" strokeWidth="1.5">
          <animate attributeName="height" values="10;6;10" dur="0.4s" repeatCount="indefinite" />
        </rect>
      ) : (
        <rect x="52" y="68" width="24" height="4" rx="2" fill="#666" />
      )}
      {/* Body — sturdy brick */}
      <rect x="32" y="80" width="64" height="38" rx="4" fill="#A0A0A0" stroke="#707070" strokeWidth="2" />
      {/* Brick pattern */}
      <line x1="32" y1="92" x2="96" y2="92" stroke="#888" strokeWidth="1" />
      <line x1="32" y1="104" x2="96" y2="104" stroke="#888" strokeWidth="1" />
      <line x1="64" y1="80" x2="64" y2="92" stroke="#888" strokeWidth="1" />
      <line x1="48" y1="92" x2="48" y2="104" stroke="#888" strokeWidth="1" />
      <line x1="80" y1="92" x2="80" y2="104" stroke="#888" strokeWidth="1" />
    </svg>
  ),
  bishop: (speaking) => (
    <svg viewBox="0 0 128 128" className="w-full h-full">
      {/* Mitre hat */}
      <path d="M 64,8 L 46,48 Q 64,52 82,48 Z" fill="#7B3FA0" stroke="#5B2D80" strokeWidth="2" />
      <line x1="64" y1="12" x2="64" y2="46" stroke="#FFD700" strokeWidth="2" />
      <line x1="50" y1="34" x2="78" y2="34" stroke="#FFD700" strokeWidth="2" />
      <circle cx="64" cy="34" r="3" fill="#FFD700" />
      {/* Head */}
      <ellipse cx="64" cy="62" rx="24" ry="20" fill="#FFE0BD" stroke="#D4A574" strokeWidth="2" />
      {/* Eyes — wise, slightly narrowed */}
      <ellipse cx="54" cy="58" rx="4.5" ry="4" fill="white" />
      <ellipse cx="74" cy="58" rx="4.5" ry="4" fill="white" />
      <circle cx="55" cy="59" r="2.5" fill="#0D47A1" />
      <circle cx="75" cy="59" r="2.5" fill="#0D47A1" />
      <circle cx="55.5" cy="57.5" r="1" fill="white" />
      <circle cx="75.5" cy="57.5" r="1" fill="white" />
      {/* Spectacles */}
      <circle cx="54" cy="58" r="7" fill="none" stroke="#8B7355" strokeWidth="1.5" />
      <circle cx="74" cy="58" r="7" fill="none" stroke="#8B7355" strokeWidth="1.5" />
      <line x1="61" y1="58" x2="67" y2="58" stroke="#8B7355" strokeWidth="1.5" />
      {/* Eyebrows */}
      <path d="M 46,50 Q 54,46 62,50" fill="none" stroke="#666" strokeWidth="2" strokeLinecap="round" />
      <path d="M 66,50 Q 74,46 82,50" fill="none" stroke="#666" strokeWidth="2" strokeLinecap="round" />
      {/* Mouth */}
      {speaking ? (
        <ellipse cx="64" cy="74" rx="6" ry="5" fill="#CC6666" stroke="#994444" strokeWidth="1.5">
          <animate attributeName="ry" values="5;3;5" dur="0.45s" repeatCount="indefinite" />
        </ellipse>
      ) : (
        <path d="M 58,72 Q 64,78 70,72" fill="none" stroke="#8B4513" strokeWidth="2" strokeLinecap="round" />
      )}
      {/* Body — vestments */}
      <path d="M 40,82 Q 64,78 88,82 L 94,118 L 34,118 Z" fill="#7B3FA0" stroke="#5B2D80" strokeWidth="2" />
      <line x1="64" y1="82" x2="64" y2="118" stroke="#FFD700" strokeWidth="2" />
      {/* Cross pendant */}
      <line x1="64" y1="86" x2="64" y2="96" stroke="#FFD700" strokeWidth="3" />
      <line x1="59" y1="90" x2="69" y2="90" stroke="#FFD700" strokeWidth="3" />
    </svg>
  ),
  knight: (speaking) => (
    <svg viewBox="0 0 128 128" className="w-full h-full">
      {/* Mane */}
      <path d="M 68,12 Q 78,14 82,24 Q 86,34 84,48" fill="#8B5E3C" stroke="#6B4226" strokeWidth="2" />
      <path d="M 66,16 Q 74,18 78,28 Q 82,38 80,50" fill="#A0724E" stroke="#6B4226" strokeWidth="1" />
      {/* Horse head */}
      <path d="M 34,50 Q 28,36 36,22 Q 44,12 60,12 Q 72,12 76,24 L 82,48 Q 84,58 78,66 L 68,76 Q 60,80 48,78 Q 36,76 32,66 Z" fill="#C8956C" stroke="#8B5E3C" strokeWidth="2" />
      {/* Ear */}
      <path d="M 50,14 L 44,4 L 40,16" fill="#C8956C" stroke="#8B5E3C" strokeWidth="2" />
      <path d="M 48,14 L 44,8 L 42,16" fill="#FFB6A0" strokeWidth="0" />
      {/* Eye — big, goofy */}
      <ellipse cx="48" cy="36" rx="9" ry="10" fill="white" stroke="#8B5E3C" strokeWidth="1.5" />
      <circle cx="50" cy="38" r="6" fill="#2D1B00" />
      <circle cx="52" cy="35" r="2.5" fill="white" />
      {/* Nostril */}
      <ellipse cx="34" cy="58" rx="4" ry="3" fill="#8B5E3C" />
      <ellipse cx="42" cy="60" rx="4" ry="3" fill="#8B5E3C" />
      {/* Mouth */}
      {speaking ? (
        <g>
          <path d="M 34,66 Q 42,76 56,72" fill="#CC7766" stroke="#8B5E3C" strokeWidth="2">
            <animate attributeName="d" values="M 34,66 Q 42,76 56,72;M 34,66 Q 42,70 56,68;M 34,66 Q 42,76 56,72" dur="0.4s" repeatCount="indefinite" />
          </path>
          <path d="M 38,70 L 50,68" fill="none" stroke="white" strokeWidth="1" />
        </g>
      ) : (
        <path d="M 34,66 Q 42,72 56,68" fill="none" stroke="#8B5E3C" strokeWidth="2" strokeLinecap="round" />
      )}
      {/* Body — armored */}
      <path d="M 32,78 Q 28,80 26,86 L 22,118 L 100,118 L 96,86 Q 94,80 88,78 Q 64,72 32,78 Z" fill="#708090" stroke="#556070" strokeWidth="2" />
      {/* Shield emblem */}
      <path d="M 54,88 L 64,84 L 74,88 L 74,102 Q 64,108 54,102 Z" fill="#4A6FA5" stroke="#3A5F95" strokeWidth="1.5" />
      <path d="M 64,88 L 64,102" stroke="#FFD700" strokeWidth="1.5" />
      <path d="M 56,94 L 72,94" stroke="#FFD700" strokeWidth="1.5" />
    </svg>
  ),
  pawn: (speaking) => (
    <svg viewBox="0 0 128 128" className="w-full h-full">
      {/* Helmet */}
      <ellipse cx="64" cy="32" rx="22" ry="20" fill="#708090" stroke="#556070" strokeWidth="2" />
      <path d="M 42,32 Q 42,16 64,12 Q 86,16 86,32" fill="#808890" stroke="#556070" strokeWidth="1.5" />
      {/* Helmet crest */}
      <path d="M 62,12 Q 64,4 66,12" fill="#CC4444" stroke="#AA2222" strokeWidth="1.5" />
      <ellipse cx="64" cy="6" rx="3" ry="4" fill="#CC4444" />
      {/* Face opening */}
      <ellipse cx="64" cy="40" rx="16" ry="12" fill="#FFE0BD" stroke="#D4A574" strokeWidth="1.5" />
      {/* Eyes — wide, determined */}
      <ellipse cx="58" cy="38" rx="3.5" ry="4" fill="white" />
      <ellipse cx="70" cy="38" rx="3.5" ry="4" fill="white" />
      <circle cx="59" cy="39" r="2.2" fill="#4A2810" />
      <circle cx="71" cy="39" r="2.2" fill="#4A2810" />
      <circle cx="59.5" cy="37.5" r="0.8" fill="white" />
      <circle cx="71.5" cy="37.5" r="0.8" fill="white" />
      {/* Eyebrows — determined */}
      <path d="M 53,34 L 62,33" stroke="#5C3A1E" strokeWidth="2" strokeLinecap="round" />
      <path d="M 75,34 L 66,33" stroke="#5C3A1E" strokeWidth="2" strokeLinecap="round" />
      {/* Mouth */}
      {speaking ? (
        <ellipse cx="64" cy="47" rx="5" ry="4" fill="#CC6666" stroke="#994444" strokeWidth="1">
          <animate attributeName="ry" values="4;2;4" dur="0.35s" repeatCount="indefinite" />
        </ellipse>
      ) : (
        <path d="M 60,46 Q 64,50 68,46" fill="none" stroke="#8B4513" strokeWidth="1.5" strokeLinecap="round" />
      )}
      {/* Body — small soldier tunic */}
      <path d="M 38,54 Q 36,56 34,62 L 28,118 L 100,118 L 94,62 Q 92,56 90,54 Q 64,48 38,54 Z" fill="#2E7D32" stroke="#1B5E20" strokeWidth="2" />
      {/* Belt */}
      <rect x="34" y="76" width="60" height="6" rx="2" fill="#8B5E3C" stroke="#6B4226" strokeWidth="1" />
      <rect x="60" y="74" width="8" height="10" rx="2" fill="#FFD700" stroke="#B8860B" strokeWidth="1" />
      {/* Tunic cross */}
      <line x1="64" y1="58" x2="64" y2="76" stroke="#FFD700" strokeWidth="2" />
      <line x1="50" y1="66" x2="78" y2="66" stroke="#FFD700" strokeWidth="2" />
    </svg>
  ),
}

const pieceEmojis: Record<string, string> = {
  king: '\u265A',
  queen: '\u265B',
  rook: '\u265C',
  bishop: '\u265D',
  knight: '\u265E',
  pawn: '\u265F',
}

export function PieceCharacter({ pieceType, isSpeaking = false }: PieceCharacterProps) {
  const type = pieceType.toLowerCase()
  const renderCharacter = characterSvgs[type]
  const pieceName = type.charAt(0).toUpperCase() + type.slice(1)

  return (
    <div className="flex flex-col items-center gap-2">
      <div className={`relative w-32 h-32 ${isSpeaking ? 'animate-bounce-subtle' : ''}`}>
        {/* Glow effect when speaking */}
        {isSpeaking && (
          <div className="absolute inset-0 rounded-full bg-blue-500/20 blur-xl animate-pulse" />
        )}
        <div className="relative">
          {renderCharacter ? (
            renderCharacter(isSpeaking)
          ) : (
            <div className="w-32 h-32 flex items-center justify-center text-6xl">
              {pieceEmojis[type] || '\u265E'}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-lg font-semibold text-white">{pieceName}</span>
        {isSpeaking && (
          <span className="flex gap-1">
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </span>
        )}
      </div>
    </div>
  )
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
          {'\uD83E\uDD16'}
        </span>
      )}
    </div>
  )
}
