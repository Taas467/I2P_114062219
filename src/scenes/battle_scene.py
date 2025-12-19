import pygame as pg
import os
from src.scenes.scene import Scene
from src.core.services import scene_manager, sound_manager, resource_manager
from src.utils import Logger, GameSettings
from typing import override
from src.interface.components import Button
import re
import random
import json


class BattleScene(Scene):
    def __init__(self):
        super().__init__()
        # Minimal battle state; will be initialized in enter()
        self.game_manager = None  # the EnemyTrainer or wild monster being battled
        self.player_name = "unknown"
        self.player_base = 1
        self.player_hp = 100
        self.player_max = 100
        self.player_sprite = "attack/attack1.png"
        self.player_level = 1
        self.player_exp = 0
        self.dmg = 0
        self.sdmg = 0
        self.buf = 1.0  # damage multiplier buffer
        self.player_property = "Normal"

        self.pkm_select = 0

        self.enemy_name = "unknown"
        self.enemy_base = 1
        self.enemy_hp = 100
        self.enemy_max = 100
        self.enemy_sprite = "attack/attack1.png"
        self.enemy_level = 1
        self.enemy_dmg = 0
        self.enemy_buf = 1.0
        self.enemy_property = "Normal"

        self.turn = "player"  # 'player' or 'enemy'
        self.font = pg.font.SysFont(None, 28)
        # UI assets (loaded in init so we can reuse)
        self.bg_img = resource_manager.get_image("backgrounds/background1.png")
        self.ui_frame = resource_manager.get_image("UI/raw/UI_Flat_Frame03a.png")
        self.button_img = resource_manager.get_image("UI/raw/UI_Flat_Button02a_1.png")
        # banner image to place behind sprites
        self.banner_img = resource_manager.get_image("UI/raw/UI_Flat_Banner03a.png")
        # small name frame for labels
        self.name_frame = resource_manager.get_image("UI/raw/UI_Flat_Frame01a.png")

        # Buttons area (four actions)
        btn_w, btn_h = 160, 44
        gap = 20
        total_w = btn_w * 4 + gap * 3
        start_x = (GameSettings.SCREEN_WIDTH - total_w) // 2
        # move buttons slightly lower so they don't overlap the info text
        y = GameSettings.SCREEN_HEIGHT - 80
        self.button_rects = [
            pg.Rect(start_x + i * (btn_w + gap), y, btn_w, btn_h) for i in range(4)
        ]
        # create Button components with hover/pressed effects
        self.action_buttons: list[Button] = []
        btn_paths = [
            ("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png"),
            ("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png"),
            ("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png"),
            ("UI/raw/UI_Flat_Button02a_1.png", "UI/raw/UI_Flat_Button02a_2.png"),
        ]
        for i, rect in enumerate(self.button_rects):
            default_path, hover_path = btn_paths[i]
            # on_click handlers will be bound later in enter()
            btn = Button(
                default_path, hover_path, rect.x, rect.y, rect.w, rect.h, on_click=None
            )
            self.action_buttons.append(btn)
        self.info = {
            "text": "What will Player do?",
        }
        # thumbnails (small icons next to names)
        self.player_thumb = None
        self.enemy_thumb = None
        # message_phase: 0 idle, 2 enemy follow-up pending after player's immediate action
        self.message_timer = 0.0
        self.message_phase = 0

        self.pending_enemy_attack = False
        self.turn = "player"
        self.message_queue = []  # queue of messages to display sequentially

    def buf_calculator(self):
        with open("src/data/type_effectiveness.json", "r") as f:
            type_chart = json.load(f)
        self.buf = type_chart[self.player_property].get(self.enemy_property, 1.0)
        self.enemy_buf = type_chart[self.enemy_property].get(self.player_property, 1.0)

    @override
    def enter(self) -> None:
        self.turn = "player"
        Logger.info("Entering battle scene")
        # initialize battle state from scene_manager.battle_target if present
        target = getattr(scene_manager, "battle_target", None)
        manager = getattr(target, "game_manager", None)
        if manager is None:
            Logger.error("Failed to load game manager")
            exit(1)
        self.game_manager = manager
        Logger.info(
            f"Battle initialized: player_hp={self.player_hp}, enemy_hp={self.enemy_hp}"
        )

        self.pkm_select = self.game_manager.bag.get_pkmsel()
        target = getattr(scene_manager, "battle_target", None)
        if target is not None:
            # detailed stats from trainer
            self.enemy_name = getattr(target, "name", self.enemy_name)
            self.enemy_base = getattr(target, "base", self.enemy_base)
            self.enemy_level = getattr(target, "level", self.enemy_level)
            self.enemy_max = self.game_manager.hp_cal(self.enemy_base, self.enemy_level)
            self.enemy_hp = self.enemy_max
            self.enemy_dmg = self.game_manager.atk_cal(
                self.enemy_base, self.enemy_level
            )
            self.enemy_property = getattr(target, "property", "Normal")
            self.enemy_sprite = target.sprite_path

            players_pkm = self.game_manager.bag.get_monster(id=self.pkm_select)
            # get player stats
            self.player_name = players_pkm.get("name", self.player_name)
            self.player_base = players_pkm.get("base", self.player_base)
            self.player_level = players_pkm.get("level", self.player_level)
            self.player_max = self.game_manager.hp_cal(
                self.player_base, self.player_level
            )
            self.player_hp = min(players_pkm.get("hp", self.player_hp),self.player_max)
            self.dmg = self.game_manager.atk_cal(self.player_base, self.player_level)
            self.sdmg = int(self.dmg * 1.5)
            self.player_sprite = players_pkm.get("sprite_path", self.player_sprite)
            self.player_property = players_pkm.get("property", "Normal")
            self.player_exp = players_pkm.get("exp", 0)

            self.buf_calculator()

        def make_click(i):

            def Fight():
                if self.turn != "player":
                    return

                dmg = max(int(self.dmg * self.buf), self.dmg + 1)
                msg = f"Player do {dmg} damage."
                if 1 < self.buf < 1.4:
                    msg += " effective!"
                elif self.buf == 1.4:
                    msg += " Super effective!"
                elif self.buf < 1:
                    msg += " Seen not very effective!"
                self.enemy_hp = max(0, self.enemy_hp - dmg)

                if self.enemy_hp <= 0:
                    msg += " \nEnemy defeated!"
                    if getattr(target, "is_wild", False):
                        monster = {
                            "name": self.enemy_name,
                            "base": self.enemy_base,
                            "level": self.enemy_level,
                            "exp": 0,
                            "max_hp": self.enemy_max,
                            "hp": self.enemy_max,
                            "atk":self.enemy_dmg,
                            "property": self.enemy_property,
                            "sprite_path": self.enemy_sprite,
                        }

                        try:
                            self.game_manager.bag.add_monster(monster)
                            msg += " Added to bag!"
                        except:
                            pass
                    else:
                        self.game_manager.bag.update_item(
                            {"count": self.game_manager.bag.get_coins() + 20}, 1
                        )
                    self.push_message("battle end!", 1.2, self.back2game)
                    return

                self.turn = "enemy"
                self.push_message(msg, 1.2, self.start_enemy_attack_sequence)

            def Special():
                if self.turn != "player":
                    return
                dmg = max(int(self.sdmg * self.buf), self.sdmg + 1)
                msg = "Emotional Damage! Ha Ha!"

                self.enemy_hp = max(0, self.enemy_hp - dmg)
                if 1 < self.buf < 1.4:
                    msg += " effective!"
                elif self.buf == 1.4:
                    msg += " Super effective!"
                elif self.buf < 1:
                    msg += " Seen not very effective!"

                if self.enemy_hp <= 0:
                    msg += " \nEnemy defeated!"
                    if getattr(target, "is_wild", False):
                        monster = {
                            "name": self.enemy_name,
                            "base": self.enemy_base,
                            "level": self.enemy_level,
                            "exp": 0,
                            "max_hp": self.enemy_max,
                            "hp": self.enemy_max,
                            "property": self.enemy_property,
                            "sprite_path": self.enemy_sprite,
                        }
                        try:
                            self.game_manager.bag.add_monster(monster)
                            msg += " Added to bag!"
                        except:
                            pass
                    else:
                        self.game_manager.bag.update_item(
                            {"count": self.game_manager.bag.get_coins() + 20}, 1
                        )
                    self.push_message("battle end!", 1.2, self.back2game)
                    return

                self.turn = "enemy"
                self.push_message(msg, 1.2, self.start_enemy_attack_sequence)

            def Magic():
                if self.turn != "player":
                    return
                self.info = {"text": "but we didn't have this function..."}

            def Run():
                if self.turn != "player":
                    return
                self.game_manager.update_run(True)
                self.push_message("Player ran away!", 1.2, self.back2game)

            def wrapped():
                if self.message_queue:
                    return  # message 出現中，禁止所有行動

                actions = [Fight, Special, Magic, Run]
                return actions[i]()

            return wrapped

        # 綁定按鈕
        for idx, btn in enumerate(self.action_buttons):
            btn.on_click = make_click(idx)

    @override
    def exit(self) -> None:
        # cleanup if needed
        if hasattr(scene_manager, "battle_target"):
            delattr(scene_manager, "battle_target")

    def push_message(self, text: str, display_time: float = 1.2, callback=None):
        """加入要顯示的訊息，callback 在訊息顯示完畢後執行"""
        self.message_queue.append(
            {
                "text": text,
                "time": display_time,
                "callback": callback,
            }
        )

    def start_enemy_attack_sequence(self):
        """敵人攻擊流程：放入訊息 queue"""

        def backplayer():
            self.turn = "player"

        dmg = max(int(self.enemy_dmg * self.enemy_buf), self.enemy_dmg + 1)
        msg = f"Enemy hits Player for {dmg}!"
        if 1 < self.enemy_buf < 1.4:
            msg += " effective!"
        elif self.enemy_buf == 1.4:
            msg += " Super effective!"
        elif self.enemy_buf < 1:
            msg += " Seen not very effective!"
        self.player_hp = max(0, self.player_hp - dmg)
        Logger.info(f"Battle: enemy attacked player for {dmg}, hp={self.player_hp}")
        if self.player_hp <= 0:
            self.player_hp = self.player_max
            self.push_message(f"{msg} Player defeated!", 1.5, self.back2game)
            self.game_manager.update_run(True)
            return

        self.push_message(msg, 1.2, backplayer)

    @override
    def update(self, dt: float) -> None:
        # 讓按鈕更新（事件檢查）
        for b in self.action_buttons:
            try:
                b.update(dt)
            except Exception:
                pass

        # 無訊息 → 不做事
        if not self.message_queue:
            self.info = {"text": "What will Player do?"}
            return

        self.info = self.message_queue[0]

        # 初始化顯示時間
        if "remaining" not in self.info:
            self.info["remaining"] = self.info["time"]

        # 倒數
        self.info["remaining"] -= dt
        if self.info["remaining"] > 0:
            return

        # 倒數完 → 執行 callback（如果有）
        callback = self.info.get("callback")
        if callback != None:
            callback()
        self.message_queue.pop(0)

    @override
    def draw(self, screen: pg.Surface) -> None:
        # Draw background image if available
        if self.bg_img:
            try:
                bg = pg.transform.scale(
                    self.bg_img, (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT)
                )
                screen.blit(bg, (0, 0))
            except Exception:
                screen.fill((30, 30, 60))
        else:
            screen.fill((30, 30, 60))
        sprite_w, sprite_h = 180, 180
        center_x = GameSettings.SCREEN_WIDTH // 2
        center_y = GameSettings.SCREEN_HEIGHT // 2 - 40
        # Enemy placed to the right of center, slightly higher
        ex = center_x + 80
        ey = center_y - 160
        if self.enemy_sprite:
            try:
                # 使用上方的 (sprite_w, sprite_h) 對敵方精靈做縮放，控制顯示大小
                eimg = resource_manager.get_image(self.enemy_sprite)
                es = pg.transform.scale(eimg, (sprite_w, sprite_h))
                # 將縮放後的敵方精靈繪製到畫面上，位置由 (ex, ey) 決定
                screen.blit(es, (ex, ey))
            except Exception:
                pg.draw.rect(screen, (150, 200, 150), (ex, ey, sprite_w, sprite_h))
        else:
            pg.draw.rect(screen, (150, 200, 150), (ex, ey, sprite_w, sprite_h))

        # Player placed to the left of center, slightly lower
        px = center_x - 250
        py = center_y + 20
        if self.player_sprite:
            try:
                # 使用上方的 (sprite_w, sprite_h) 對我方精靈做縮放，控制顯示大小
                pimg = resource_manager.get_image(self.player_sprite)
                pimg_flipped = pg.transform.flip(pimg, True, False)
                ps = pg.transform.scale(pimg_flipped, (sprite_w + 50, sprite_h + 50))
                # 將縮放後的我方精靈繪製到畫面上，位置由 (px, py) 決定
                screen.blit(ps, (px, py))
            except Exception:
                pg.draw.rect(screen, (100, 180, 200), (px, py, sprite_w, sprite_h))
        else:
            pg.draw.rect(screen, (100, 180, 200), (px, py, sprite_w, sprite_h))

        # Draw name boxes above HP like the screenshot
        # Enemy name box (top-right)
        name_box_w, name_box_h = 300, 80
        enemy_name_x = GameSettings.SCREEN_WIDTH - name_box_w - 20
        enemy_name_y = 12
        # use banner image for the name box background
        if self.banner_img:
            try:
                nb = pg.transform.scale(self.banner_img, (name_box_w, name_box_h))
                screen.blit(nb, (enemy_name_x, enemy_name_y))
            except Exception:
                pg.draw.rect(
                    screen,
                    (245, 235, 200),
                    (enemy_name_x, enemy_name_y, name_box_w, name_box_h),
                )
        elif self.name_frame:
            try:
                nf = pg.transform.scale(self.name_frame, (name_box_w, name_box_h))
                screen.blit(nf, (enemy_name_x, enemy_name_y))
            except Exception:
                pg.draw.rect(
                    screen,
                    (245, 235, 200),
                    (enemy_name_x, enemy_name_y, name_box_w, name_box_h),
                )
        else:
            pg.draw.rect(
                screen,
                (245, 235, 200),
                (enemy_name_x, enemy_name_y, name_box_w, name_box_h),
            )
        # --- 優化敵方資訊框 ---
        thumb_size = name_box_h - 8
        text_x_offset = 8
        thumb_y = enemy_name_y - 12
        if self.enemy_thumb:
            try:
                thumb_s = pg.transform.scale(self.enemy_thumb, (thumb_size, thumb_size))
                tx = enemy_name_x + 16
                screen.blit(thumb_s, (tx, thumb_y))
                text_x_offset += thumb_size + 14
            except Exception:
                pass
        # 名字
        name_font = pg.font.SysFont(None, 24, bold=True)
        name_txt = name_font.render(str(self.enemy_name), True, (10, 10, 10))
        screen.blit(name_txt, (enemy_name_x + text_x_offset, enemy_name_y + 6))
        # 等級直接顯示在右上角
        enemy_lv = getattr(self, "enemy_level", 1)
        lv_font = pg.font.SysFont(None, 24, bold=True)
        lv_txt = lv_font.render(f"Lv{int(enemy_lv)}", True, (40, 40, 40))
        screen.blit(
            lv_txt,
            (enemy_name_x + name_box_w - lv_txt.get_width() - 10, enemy_name_y + 6),
        )
        # HP bar 緊貼在名字下方
        # HP條長度維持原本比例，不拉長
        hp_w = 180
        hp_h = 10
        hp_x = enemy_name_x + text_x_offset
        hp_y = enemy_name_y + 6 + name_txt.get_height() + 6
        pg.draw.rect(screen, (120, 120, 120), (hp_x, hp_y, hp_w, hp_h))
        if self.enemy_max > 0:
            fill = int(hp_w * (self.enemy_hp / max(1, self.enemy_max)))
        else:
            fill = 0
        pg.draw.rect(screen, (40, 200, 40), (hp_x, hp_y, fill, hp_h))
        # HP 數字
        hp_font = pg.font.SysFont(None, 16)
        hp_txt = hp_font.render(f"{self.enemy_hp}/{self.enemy_max}", True, (30, 30, 30))
        screen.blit(hp_txt, (hp_x, hp_y + hp_h + 2))

        # Player name box (bottom-left, above player sprite)
        player_name_x = 20
        player_name_y = GameSettings.SCREEN_HEIGHT - 220  # 上移40px，避免被底部UI遮住
        if self.banner_img:
            try:
                nb2 = pg.transform.scale(self.banner_img, (name_box_w, name_box_h))
                screen.blit(nb2, (player_name_x, player_name_y))
            except Exception:
                pg.draw.rect(
                    screen,
                    (245, 235, 200),
                    (player_name_x, player_name_y, name_box_w, name_box_h),
                )
        elif self.name_frame:
            try:
                nf2 = pg.transform.scale(self.name_frame, (name_box_w, name_box_h))
                screen.blit(nf2, (player_name_x, player_name_y))
            except Exception:
                pg.draw.rect(
                    screen,
                    (245, 235, 200),
                    (player_name_x, player_name_y, name_box_w, name_box_h),
                )
        else:
            pg.draw.rect(
                screen,
                (245, 235, 200),
                (player_name_x, player_name_y, name_box_w, name_box_h),
            )
        # --- 優化我方資訊框 ---
        thumb_size = name_box_h - 8
        p_text_x_offset = 8
        p_thumb_y = player_name_y - 12
        if self.player_thumb:
            try:
                p_thumb_s = pg.transform.scale(
                    self.player_thumb, (thumb_size, thumb_size)
                )
                ptx = player_name_x + 16
                screen.blit(p_thumb_s, (ptx, p_thumb_y))
                p_text_x_offset += thumb_size + 4
            except Exception:
                pass
        # 名字
        p_name_font = pg.font.SysFont(None, 24, bold=True)
        p_name_txt = p_name_font.render(str(self.player_name), True, (10, 10, 10))
        screen.blit(p_name_txt, (player_name_x + p_text_x_offset, player_name_y + 6))
        # 等級直接顯示在右上角
        player_lv = getattr(self, "player_level", 1)
        p_lv_font = pg.font.SysFont(None, 24, bold=True)
        p_lv_txt = p_lv_font.render(f"Lv{int(player_lv)}", True, (40, 40, 40))
        screen.blit(
            p_lv_txt,
            (player_name_x + name_box_w - p_lv_txt.get_width() - 10, player_name_y + 6),
        )
        # HP bar 緊貼在名字下方
        php_w = name_box_w - p_text_x_offset - 16
        php_h = 10
        php_x = player_name_x + p_text_x_offset
        php_y = player_name_y + 6 + p_name_txt.get_height() + 6
        pg.draw.rect(screen, (120, 120, 120), (php_x, php_y, php_w, php_h))
        if self.player_max > 0:
            pfill = int(php_w * (self.player_hp / max(1, self.player_max)))
        else:
            pfill = 0
        pg.draw.rect(screen, (40, 200, 40), (php_x, php_y, pfill, php_h))
        # HP 數字
        p_hp_font = pg.font.SysFont(None, 16)
        p_hp_txt = p_hp_font.render(
            f"{self.player_hp}/{self.player_max}", True, (30, 30, 30)
        )
        screen.blit(p_hp_txt, (php_x, php_y + php_h + 2))

        # Draw bottom UI frame
        panel_h = 120
        panel_y = GameSettings.SCREEN_HEIGHT - panel_h
        if self.ui_frame:
            try:
                frame = pg.transform.scale(
                    self.ui_frame, (GameSettings.SCREEN_WIDTH, panel_h)
                )
                screen.blit(frame, (0, panel_y))
            except Exception:
                pg.draw.rect(
                    screen,
                    (20, 20, 20),
                    (0, panel_y, GameSettings.SCREEN_WIDTH, panel_h),
                )
        else:
            pg.draw.rect(
                screen, (20, 20, 20), (0, panel_y, GameSettings.SCREEN_WIDTH, panel_y)
            )

        # Draw action buttons (4) using Button components (shows hover/pressed)
        labels = ["Fight", "Special", "Magic", "Run"]
        for i, btn in enumerate(self.action_buttons):
            try:
                btn.draw(screen)
            except Exception:
                # fallback draw
                r = self.button_rects[i]
                if self.button_img:
                    try:
                        bsurf = pg.transform.scale(self.button_img, (r.w, r.h))
                        screen.blit(bsurf, (r.x, r.y))
                    except Exception:
                        pg.draw.rect(screen, (240, 240, 240), r)
                else:
                    pg.draw.rect(screen, (240, 240, 240), r)
            # draw label centered
            rect = self.button_rects[i]
            txt = self.font.render(labels[i], True, (20, 20, 20))
            tx = rect.x + (rect.w - txt.get_width()) // 2
            ty = rect.y + (rect.h - txt.get_height()) // 2
            screen.blit(txt, (tx, ty))

        # Info text (left of panel)
        txt = self.info.get("text", "What will Player do?")
        info_txt = self.font.render(txt, True, (255, 255, 255))
        screen.blit(info_txt, (20, panel_y + 12))

    def back2game(self):
        print(self.player_hp)
        monster = {"hp": self.player_hp, "exp": self.player_exp + 10,"atk":self.dmg}
        self.game_manager.bag.update_monster(monster, self.pkm_select)
        self.game_manager.end_battle()

        try:
            scene_manager.change_scene("game")
        except Exception:
            Logger.warning("Failed to return to game scene from battle scene")
