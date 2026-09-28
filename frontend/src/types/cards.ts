export interface CardFaceData {
  name: string;
  mana_cost: string | null;
  type_line: string | null;
  oracle_text: string | null;
  power: string | null;
  toughness: string | null;
  loyalty: string | null;
  defense: string | null;
  colors: string[] | null;
  image_face: number;
}

export interface RelatedToken {
  id: string;
  name: string;
  type_line: string | null;
}

export interface CardData {
  id: string;
  oracle_id: string;
  name: string;
  layout: string;
  set_code: string;
  set_name: string;
  collector_number: string;
  rarity: string | null;
  mana_cost: string | null;
  cmc: number | null;
  type_line: string | null;
  oracle_text: string | null;
  power: string | null;
  toughness: string | null;
  loyalty: string | null;
  defense: string | null;
  colors: string[];
  color_identity: string[];
  keywords: string[];
  is_token: boolean;
  faces: CardFaceData[];
  double_faced: boolean;
  image_faces: number;
  has_image: boolean;
  released_at?: string | null;
  artist?: string | null;
  commander_legal?: string | null;
  related_tokens?: RelatedToken[];
  related_cards?: { id: string; name: string; component: string }[];
}

export interface SearchResponse {
  results: CardData[];
  has_more: boolean;
}
