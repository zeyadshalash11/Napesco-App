# In core/log_handlers.py

import logging
import traceback # Import the traceback library
from django.conf import settings
from discord_webhook import DiscordWebhook, DiscordEmbed

class DiscordWebhookHandler(logging.Handler):
    def emit(self, record):
        try:
            webhook_url = getattr(settings, 'DISCORD_WEBHOOK_URL', None)
            if not webhook_url:
                return

            # --- NEW, SMARTER MESSAGE FORMATTING ---

            # If an exception happened, format it nicely
            if record.exc_info:
                exc_type, exc_value, exc_traceback = record.exc_info
                
                # Get the last frame of the traceback for the file and line number
                tb_frame = traceback.extract_tb(exc_traceback)[-1]
                file_name = tb_frame.filename.split('/')[-1].split('\\')[-1] # Get just the filename
                line_no = tb_frame.lineno
                
                error_title = f"🚨 Unhandled Exception: {exc_type.__name__}"
                error_description = f"**{exc_value}**\n\n"
                error_description += f"An error occurred in file `{file_name}` at line `{line_no}`."
                
                # Get the full traceback as a string
                full_traceback = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                
                # Add the traceback in a collapsible code block
                error_description += f"\n\n**Traceback:**\n```\n{full_traceback[:1500]}...\n```"

            else:
                # For non-error messages, keep it simple
                error_title = f'ℹ️ Application Log: {record.levelname}'
                error_description = self.format(record)

            # Create the embed
            embed = DiscordEmbed(
                title=error_title,
                description=error_description,
                color='E74C3C'
            )
            embed.set_timestamp()

            webhook = DiscordWebhook(url=webhook_url)
            webhook.add_embed(embed)
            response = webhook.execute()

        except Exception:
            self.handleError(record)