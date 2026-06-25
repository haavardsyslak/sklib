from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["supplier"])


@router.get("/digikey/search")
def search_digikey(mpn: str = Query(..., min_length=1)) -> JSONResponse:
    from src.supplier import DigikeyInterface

    try:
        digikey = DigikeyInterface(coverage=True)
        products = digikey.search_and_map(mpn)
        return JSONResponse({"results": [p.to_dict() for p in products]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
