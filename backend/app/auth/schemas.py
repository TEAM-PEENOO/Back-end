from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=20)


class GoogleCodeLoginRequest(BaseModel):
    code: str = Field(min_length=10)
    redirect_uri: str


class GoogleAuthUrlResponse(BaseModel):
    auth_url: str
    state: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    email: EmailStr
    name: str | None
    profile_image: str | None
    created_at: str

