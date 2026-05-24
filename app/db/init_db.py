from sqlalchemy.exc import IntegrityError
from db.base import Base
from db.session import engine
import db.models  # noqa

import os


async def init_db():
    from db.enums import UserRole
    from db.repositories.events_repo import EventRepository
    from db.session import AsyncSessionLocal

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    for role in ("ADMIN", "APPROVER", "VIEWER", "EXPERIMENTER"):
        email = os.getenv(f"{role}_EMAIL", f"{role.lower()}@mail.ru")
        password = os.getenv(f"{role}_PASSWORD", f"{role.lower()}123")

        await init_user(email, password, getattr(UserRole, role))

    async with AsyncSessionLocal() as session:
        try:
            await EventRepository.create_event_type(
                session=session,
                key="exposure",
                description="basic key for checking if an object was exposed",
                requires_exposure=False
            )

            await session.commit()

        except IntegrityError:
            pass

        except Exception as e:
            raise e


async def init_user(email, password, role):
    from db.repositories.users_repo import UserRepository
    from db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            await UserRepository.create(
                session=session,
                email=email,
                password=password,
                role=role,
                is_active=True
            )

            await session.commit()
        except IntegrityError:
            pass

        except Exception as e:
            raise e
