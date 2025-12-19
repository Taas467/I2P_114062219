from __future__ import annotations
import pygame as pg
from .entity import Entity
from src.core.services import input_manager,scene_manager
from src.utils import Position, PositionCamera, GameSettings, Logger
from src.core import GameManager
import math
from typing import override
import random
from types import SimpleNamespace
import json
class Player(Entity):
    speed: float = 4.0 * GameSettings.TILE_SIZE
    game_manager: GameManager

    def __init__(self, x: float, y: float, game_manager: GameManager) -> None:
        super().__init__(x, y, game_manager)
        self.happy_map_info=False
        with open("src/pokemon.json", "r") as f:
            self.pokemon_data = json.load(f)
        self.evolution_data=self.pokemon_data["evolution"]
        
   

    @override
    def update(self, dt: float) -> None:
        '''
        [TODO HACKATHON 2]
        Calculate the distance change, and then normalize the distance
        '''
        '''
        [TODO HACKATHON 4]
        Check if there is collision, if so try to make the movement smooth
        Hint #1 : use entity.py _snap_to_grid function or create a similar function
        Hint #2 : Beware of glitchy teleportation, you must do
                    1. Update X
                    2. If collide, snap to grid
                    3. Update Y
                    4. If collide, snap to grid
                  instead of update both x, y, then snap to grid
        '''
        dis = pg.Vector2(0, 0)

        # 輸入
        if input_manager.key_down(pg.K_LEFT) or input_manager.key_down(pg.K_a):
            dis.x -= 1
        if input_manager.key_down(pg.K_RIGHT) or input_manager.key_down(pg.K_d):
            dis.x += 1
        if input_manager.key_down(pg.K_UP) or input_manager.key_down(pg.K_w):
            dis.y -= 1
        if input_manager.key_down(pg.K_DOWN) or input_manager.key_down(pg.K_s):
            dis.y += 1

        
        if dis.length() > 0:
            dis = dis.normalize()
        if not self.happy_map_info and self.game_manager.in_happy():
            print("in the happy map! Have funny!")
            self.happy_map_info=True
            self.game_manager.save("saves/game0.json")


        # 位移
        move_x = dis.x * self.speed * dt
        move_y = dis.y * self.speed * dt 
        hit_enemy=False
        if not self.game_manager.in_happy():
            move_x *=3
            move_y *=3
        
        # X 軸移動 
        self.position.x += move_x
        self.animation.update_pos(self.position)  # 更新 hitbox /動畫位置
        if self.game_manager.current_map.check_collision(self.animation.rect):
            self.position.x = self._snap_to_grid(self.position.x)
        for enemy in self.game_manager.current_enemy_trainers:
            if self.animation.rect.colliderect(enemy.get_hitbox()):
                self.position.x = self._snap_to_grid(self.position.x)
                enemy.detected = True
                hit_enemy = True

        # Y 軸移動  
        self.position.y += move_y
        self.animation.update_pos(self.position)
        if self.game_manager.current_map.check_collision(self.animation.rect):
            self.position.y = self._snap_to_grid(self.position.y)
        for enemy in self.game_manager.current_enemy_trainers:
            if self.animation.rect.colliderect(enemy.get_hitbox()):
                self.position.y = self._snap_to_grid(self.position.y)
                enemy.detected = True
                hit_enemy = True


        if hit_enemy:
            pass

        # 檢查傳送點
        tp = self.game_manager.current_map.check_teleport(self.position)
        if tp:
            dest = tp.destination
            self.game_manager.switch_map(dest)
        
        try:
            # 計算所在的 tile 座標
            tx = int(self.position.x) // GameSettings.TILE_SIZE
            ty = int(self.position.y) // GameSettings.TILE_SIZE
            current_tile = (tx, ty)

            # 是否在草叢上
            in_bush = self.game_manager.current_map.is_pokemon_bush_at(self.position)

            if in_bush:
                # 如果進入新的草叢 tile（不管之前是否在草叢）
                if self._last_bush_tile != current_tile:

                    # Just entered a NEW bush tile — spawn a random wild pokemon

                    candidates = self.pokemon_data.get("candidates", [])
                    wild = random.choice(candidates)

                    target = SimpleNamespace()
                    target.game_manager = self.game_manager
                    target.name= wild.get("name","unknow")
                    target.base= wild.get("base",1)
                    target.level= wild.get("level",1)
                    target.property= wild.get("property","Normal")
                    target.sprite_path = wild.get("sprite_path")
                    target.hp = wild.get("hp", 10)
                    target.is_wild = True

                    try:
                        setattr(scene_manager, "battle_target", target)
                        scene_manager.change_scene("battle")
                    except Exception:
                        Logger.warning("Failed to start wild battle via scene_manager")

                # 更新當前所在草 tile
                self._last_bush_tile = current_tile

            else:
                # 不在草叢 → 清空
                self._last_bush_tile = None

        except Exception:
            pass
        
        if self.game_manager.battle_end_search():
            self.game_manager.delmode_battle()
            self.game_manager.bag.level_up()
            #evolution
            id=self.game_manager.bag.get_pkmsel()
            moster=self.game_manager.bag.get_monster(id)
            exmoster=moster
            evo=self.evolution_data[moster["name"]]
            if evo["can"] and moster["level"]>=evo["level"]:
                      exmoster["name"]=evo["evolution_name"]
                      exmoster["base"]=evo["evolution_base"]
                      exmoster["property"]=evo["evolution_property"]
                      exmoster["sprite_path"]=evo["evolution_sprite_path"]
                      exmoster["max_hp"]=self.game_manager.hp_cal(moster["base"],moster["level"])
                      exmoster["hp"]=moster["max_hp"]
                      info={"remaining":2,"text":f"{moster['name']} evolves into {exmoster['name']}"}
                      self.game_manager.update_gscene(info)
                      self.game_manager.bag.update_monster(exmoster,id)



            if self.game_manager.in_happy() and self.game_manager.is_run():
                self.game_manager.update_run(False)
                self.lol()

        super().update(dt)

    def camera(self) -> PositionCamera:
        """
        Camera that keeps player centered and clamps to map size.
        """
        from src.utils import PositionCamera, GameSettings

        cam_x = int(self.position.x - GameSettings.SCREEN_WIDTH / 2)
        cam_y = int(self.position.y - GameSettings.SCREEN_HEIGHT / 2)

        # clamp
        cam_x = max(0, min(cam_x, self.game_manager.current_map.width_in_pixels - GameSettings.SCREEN_WIDTH))
        cam_y = max(0, min(cam_y, self.game_manager.current_map.height_in_pixels - GameSettings.SCREEN_HEIGHT))

        return PositionCamera(cam_x, cam_y)

    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)
        self.game_manager.current_map.draw_minimap(self.position,screen)
        
        
    @override
    def to_dict(self) -> dict[str, object]:
        return super().to_dict()
    
    @classmethod
    @override
    def from_dict(cls, data: dict[str, object], game_manager: GameManager) -> Player:
        return cls(data["x"] * GameSettings.TILE_SIZE, data["y"] * GameSettings.TILE_SIZE, game_manager)
    
    def lol(self):
        """Teleport player to a specific TILE coordinate."""
        self.position.x = 4 * GameSettings.TILE_SIZE
        self.position.y = 3 * GameSettings.TILE_SIZE
        self.animation.update_pos(self.position)
        self.game_manager.save("saves/game0.json")
    


