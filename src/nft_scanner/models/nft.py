"""NFT data model class."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class NFT:
    """Represents an NFT with its properties."""

    id: int
    name: str
    full_id: str
    gift_name: str
    image_url: str
    image_type: str
    rarity: Dict[str, Dict[str, str]] = field(default_factory=dict)
    is_super_rare: bool = False
    is_rare: bool = False
    super_rare_properties: List[str] = field(default_factory=list)
    rare_properties: List[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        """Return the URL to the NFT."""
        return f"https://t.me/nft/{self.gift_name}-{self.id}"

    @property
    def filename(self) -> str:
        """Return the filename for the NFT image."""
        return (
            f"{self.gift_name.lower()}-{self.name.lower().replace(' ', '-')}-{self.id}"
        )

    @property
    def file_extension(self) -> str:
        """Return the file extension for the NFT image."""
        return (
            ".tgs"
            if self.image_type == "tgs"
            else ".svg"
            if self.image_type == "svg"
            else ".png"
        )

    def determine_super_rarity(self) -> None:
        """
        Determine if this NFT has a super rare or rare model.
        Super rare: rarity < 0.6%
        Rare: 0.6% <= rarity < 1.8%
        Only considers the Model property, not other properties.
        """
        self.is_super_rare = False
        self.is_rare = False
        self.super_rare_properties = []
        self.rare_properties = []

        # Only check Model property for rarity
        if not self.rarity or "Model" not in self.rarity:
            return

        model_info = self.rarity["Model"]
        model_rarity = model_info.get("rarity")

        if not model_rarity:
            return

        try:
            rarity_text = model_rarity.strip().replace("%", "").replace(",", ".")
            rarity_value = float(rarity_text)
            model_name = model_info.get("value", "")

            if rarity_value < 0.6:
                self.is_super_rare = True
                self.super_rare_properties.append(
                    f"Model: {model_name} ({model_rarity})"
                )
            elif rarity_value < 1.8:
                self.is_rare = True
                self.rare_properties.append(f"Model: {model_name} ({model_rarity})")
        except (ValueError, TypeError):
            pass
