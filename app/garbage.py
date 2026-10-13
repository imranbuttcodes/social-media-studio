# from pydantic import BaseModel, Field, model_validator
# from typing import Optional

# class PostCreate(BaseModel):
#     title: str = Field(..., min_length=3, max_length=255, description="Title of the article")
#     content: Optional[str] = Field(None, description="Markdown body of the article")
#     source_url: Optional[str] = Field("None", description="URL to scrape/fetch article from")

#     @model_validator(mode="after")
#     def check_content_or_url(self):
#         if not self.content and not self.source_url:
#             raise ValueError("Either 'content' (Markdown) or 'source_url' must be provided.")
#         return self


# bro = PostCreate(title="Imran butt")

# print(bro.title)
# print(bro.content)
# print(bro.source_url)


from pydantic import BaseModel, ConfigDict

class User:
    def __init__(self, id, age):
        self.id = id
        self.age = age



user= User(id="23", age=12)

class Response(BaseModel):
   
    id: str
    age: int

    # class Config:
    #     from_attributes = True

    model_config = ConfigDict(from_attributes=True)

print(user)

response = Response.model_validate(user)


print(response)
